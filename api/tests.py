import hashlib
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from patients.auth_security import current_auth_version
from patients.models import (
    AuditEvent,
    CallLog,
    Case,
    CaseDataScope,
    DepartmentConfig,
    RoleSetting,
    StaffDeviceCredential,
    Task,
    TaskStatus,
    UserSecurityState,
    VitalEntry,
)

from .admin import MobileDeviceTokenAdmin
from .models import (
    MobileDatasetState,
    MobileDeviceToken,
    MobileNotification,
    MobileNotificationState,
    MobileNotificationType,
    MobileWriteReceipt,
)
from .notifications import invalidate_mobile_dataset, purge_expired_mobile_notifications
from .push import (
    _build_multicast_message,
    _deactivate_permanently_failed_tokens,
    firebase_configured,
    send_mobile_notification,
)
from .views import (
    _authorization_hash,
    _case_edit_payload,
    _idempotency_key_digest,
    _task_edit_values,
    _vital_edit_values,
    _serialize_notification,
)


class MobileApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="api-admin",
            email="api-admin@example.com",
            password="pass",
        )
        self.client.force_authenticate(self.user)
        self.anc, _ = DepartmentConfig.objects.get_or_create(
            name="ANC",
            defaults={"auto_follow_up_days": 7},
        )
        self.case = Case.objects.create(
            uhid="UH-API-1",
            first_name="Priya",
            last_name="Sharma",
            patient_name="Priya Sharma",
            gender="F",
            age=28,
            phone_number="9876543210",
            category=self.anc,
            diagnosis="Pregnancy",
            high_risk=True,
            anc_high_risk_reasons=["AGE_OVER_35"],
            created_by=self.user,
        )
        self.task = Task.objects.create(
            case=self.case,
            title="BP recheck",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )
        self.awaiting_task = Task.objects.create(
            case=self.case,
            title="USG anomaly scan",
            due_date=timezone.localdate() + timedelta(days=3),
            status=TaskStatus.AWAITING_REPORTS,
            assigned_user=self.user,
            created_by=self.user,
        )
        MobileNotification.objects.all().delete()

    def _bound_refresh(self, user):
        mobile_device_id = str(uuid.uuid4())
        refresh = RefreshToken.for_user(user)
        refresh["auth_version"] = current_auth_version(user)
        refresh["mobile_device_id"] = mobile_device_id
        return refresh, {"mobile_device_id": mobile_device_id}

    def test_me_returns_user_and_capabilities(self):
        response = self.client.get(reverse("api:me"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "api-admin")
        self.assertTrue(response.json()["capabilities"]["task_edit"])

    def test_token_obtain_refresh_and_me_work_with_real_jwt(self):
        mobile_user = get_user_model().objects.create_user(username="mobile-jwt", password="pass")
        client = APIClient()

        token_response = client.post(
            reverse("api:token_obtain_pair"),
            {"username": "mobile-jwt", "password": "pass"},
            format="json",
        )

        self.assertEqual(token_response.status_code, 200)
        self.assertIn("access", token_response.json())
        self.assertIn("refresh", token_response.json())

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.json()['access']}")
        me_response = client.get(reverse("api:me"))

        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["username"], mobile_user.username)

        refresh_response = client.post(
            reverse("api:token_refresh"),
            {"refresh": token_response.json()["refresh"]},
            format="json",
        )

        self.assertEqual(refresh_response.status_code, 200)
        self.assertIn("access", refresh_response.json())

    def test_case_api_denies_real_jwt_user_without_case_data_role(self):
        get_user_model().objects.create_user(username="no-case-role", password="pass")
        client = APIClient()
        token_response = client.post(
            reverse("api:token_obtain_pair"),
            {"username": "no-case-role", "password": "pass"},
            format="json",
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.json()['access']}")

        response = client.get(reverse("api:case_list"), {"bucket": "today", "assigned_to": "all"})

        self.assertEqual(response.status_code, 403)

    def test_case_api_scopes_real_jwt_non_doctor_with_case_data_role_to_assigned_tasks(self):
        mobile_user = get_user_model().objects.create_user(username="mobile-role", password="pass")
        RoleSetting.objects.create(
            role_name="Mobile Staff",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_task_edit=True,
        )
        group = Group.objects.create(name="Mobile Staff")
        mobile_user.groups.add(group)
        assigned_case = Case.objects.create(
            uhid="UH-API-ASSIGNED-MOBILE",
            first_name="Assigned",
            last_name="Mobile",
            patient_name="Assigned Mobile",
            gender="F",
            age=30,
            phone_number="9876543211",
            category=self.anc,
            diagnosis="Assigned mobile review",
            created_by=self.user,
        )
        Task.objects.create(
            case=assigned_case,
            title="Assigned mobile task",
            due_date=timezone.localdate(),
            assigned_user=mobile_user,
            created_by=self.user,
        )
        client = APIClient()
        token_response = client.post(
            reverse("api:token_obtain_pair"),
            {"username": "mobile-role", "password": "pass"},
            format="json",
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.json()['access']}")

        response = client.get(reverse("api:case_list"), {"bucket": "today", "assigned_to": "all"})

        self.assertEqual(response.status_code, 200)
        uhids = {row["uhid"] for row in response.json()["results"]}
        self.assertIn("UH-API-ASSIGNED-MOBILE", uhids)
        self.assertNotIn("UH-API-1", uhids)

    def test_case_list_blank_assigned_to_uses_default_scope_for_non_doctor_role(self):
        mobile_user = get_user_model().objects.create_user(username="blank-scope-mobile", password="pass")
        RoleSetting.objects.update_or_create(
            role_name="Blank Scope Staff",
            defaults={"case_data_scope": CaseDataScope.ASSIGNED, "can_task_edit": True},
        )
        staff_group, _ = Group.objects.get_or_create(name="Blank Scope Staff")
        mobile_user.groups.add(staff_group)
        assigned_case = Case.objects.create(
            uhid="UH-API-BLANK-ASSIGNED",
            first_name="Blank",
            last_name="Assigned",
            patient_name="Blank Assigned",
            gender="F",
            age=30,
            phone_number="9876543218",
            category=self.anc,
            diagnosis="Assigned blank scope review",
            created_by=self.user,
        )
        Task.objects.create(
            case=assigned_case,
            title="Assigned blank scope task",
            due_date=timezone.localdate(),
            assigned_user=mobile_user,
            created_by=self.user,
        )
        unassigned_case = Case.objects.create(
            uhid="UH-API-BLANK-UNASSIGNED",
            first_name="Blank",
            last_name="Unassigned",
            patient_name="Blank Unassigned",
            gender="F",
            age=31,
            phone_number="9876543219",
            category=self.anc,
            diagnosis="Unassigned blank scope review",
            created_by=self.user,
        )
        Task.objects.create(
            case=unassigned_case,
            title="Unassigned blank scope task",
            due_date=timezone.localdate(),
            created_by=self.user,
        )
        self.client.force_authenticate(mobile_user)

        response = self.client.get(reverse("api:case_list"), {"bucket": "today", "assigned_to": ""})

        self.assertEqual(response.status_code, 200)
        uhids = {row["uhid"] for row in response.json()["results"]}
        self.assertIn("UH-API-BLANK-ASSIGNED", uhids)
        self.assertNotIn("UH-API-BLANK-UNASSIGNED", uhids)
        self.assertNotIn("UH-API-1", uhids)

    def test_case_list_calls_context_allows_note_add_role_to_use_all_scope(self):
        caller = get_user_model().objects.create_user(username="calls-scope-mobile", password="pass")
        RoleSetting.objects.update_or_create(
            role_name="Calls Scope",
            defaults={
                "case_data_scope": CaseDataScope.ASSIGNED,
                "can_access_call_queue": True,
                "can_note_add": True,
            },
        )
        calls_group, _ = Group.objects.get_or_create(name="Calls Scope")
        caller.groups.add(calls_group)
        unassigned_case = Case.objects.create(
            uhid="UH-API-CALLS-UNASSIGNED",
            first_name="Calls",
            last_name="Unassigned",
            patient_name="Calls Unassigned",
            gender="F",
            age=32,
            phone_number="9876543220",
            category=self.anc,
            diagnosis="Unassigned calls review",
            created_by=self.user,
        )
        Task.objects.create(
            case=unassigned_case,
            title="Unassigned calls task",
            due_date=timezone.localdate(),
            created_by=self.user,
        )
        future_case = Case.objects.create(
            uhid="UH-API-CALLS-FUTURE",
            first_name="Calls",
            last_name="Future",
            patient_name="Calls Future",
            gender="F",
            age=33,
            phone_number="9876543223",
            category=self.anc,
            diagnosis="Future calls review",
            created_by=self.user,
        )
        Task.objects.create(
            case=future_case,
            title="Future calls task",
            due_date=timezone.localdate() + timedelta(days=14),
            created_by=self.user,
        )
        awaiting_case = Case.objects.create(
            uhid="UH-API-CALLS-AWAITING",
            first_name="Calls",
            last_name="Awaiting",
            patient_name="Calls Awaiting",
            gender="F",
            age=34,
            phone_number="9876543224",
            category=self.anc,
            diagnosis="Awaiting calls review",
            created_by=self.user,
        )
        Task.objects.create(
            case=awaiting_case,
            title="Awaiting calls task",
            due_date=timezone.localdate(),
            status=TaskStatus.AWAITING_REPORTS,
            created_by=self.user,
        )
        self.client.force_authenticate(caller)

        normal_response = self.client.get(reverse("api:case_list"), {"bucket": "all", "assigned_to": "all"})
        calls_response = self.client.get(
            reverse("api:case_list"),
            {"bucket": "all", "assigned_to": "all", "scope_context": "calls"},
        )

        self.assertEqual(normal_response.status_code, 200)
        self.assertNotIn("UH-API-CALLS-UNASSIGNED", {row["uhid"] for row in normal_response.json()["results"]})
        self.assertEqual(calls_response.status_code, 200)
        calls_uhids = {row["uhid"] for row in calls_response.json()["results"]}
        self.assertIn("UH-API-CALLS-UNASSIGNED", calls_uhids)
        self.assertNotIn("UH-API-CALLS-FUTURE", calls_uhids)
        self.assertNotIn("UH-API-CALLS-AWAITING", calls_uhids)

    def test_case_list_calls_context_does_not_bypass_scope_without_note_add_permission(self):
        mobile_user = get_user_model().objects.create_user(username="calls-scope-blocked", password="pass")
        RoleSetting.objects.update_or_create(
            role_name="No Calls Scope",
            defaults={"case_data_scope": CaseDataScope.ASSIGNED, "can_task_edit": True},
        )
        staff_group, _ = Group.objects.get_or_create(name="No Calls Scope")
        mobile_user.groups.add(staff_group)
        assigned_case = Case.objects.create(
            uhid="UH-API-CALLS-ASSIGNED",
            first_name="Calls",
            last_name="Assigned",
            patient_name="Calls Assigned",
            gender="F",
            age=33,
            phone_number="9876543221",
            category=self.anc,
            diagnosis="Assigned calls review",
            created_by=self.user,
        )
        Task.objects.create(
            case=assigned_case,
            title="Assigned calls task",
            due_date=timezone.localdate(),
            assigned_user=mobile_user,
            created_by=self.user,
        )
        unassigned_case = Case.objects.create(
            uhid="UH-API-CALLS-BLOCKED-UNASSIGNED",
            first_name="Calls",
            last_name="Blocked",
            patient_name="Calls Blocked",
            gender="F",
            age=34,
            phone_number="9876543222",
            category=self.anc,
            diagnosis="Blocked calls review",
            created_by=self.user,
        )
        Task.objects.create(
            case=unassigned_case,
            title="Blocked calls task",
            due_date=timezone.localdate(),
            created_by=self.user,
        )
        self.client.force_authenticate(mobile_user)

        response = self.client.get(
            reverse("api:case_list"),
            {"bucket": "all", "assigned_to": "all", "scope_context": "calls"},
        )

        self.assertEqual(response.status_code, 200)
        uhids = {row["uhid"] for row in response.json()["results"]}
        self.assertIn("UH-API-CALLS-ASSIGNED", uhids)
        self.assertNotIn("UH-API-CALLS-BLOCKED-UNASSIGNED", uhids)

    def test_case_list_defaults_to_all_scope_for_doctor(self):
        doctor = get_user_model().objects.create_user(username="doctor-mobile", password="pass")
        RoleSetting.objects.update_or_create(role_name="Doctor", defaults={"case_data_scope": CaseDataScope.ALL, "can_task_edit": True})
        doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        doctor.groups.add(doctor_group)
        unassigned_case = Case.objects.create(
            uhid="UH-API-UNASSIGNED-DOCTOR",
            first_name="Unassigned",
            last_name="Doctor",
            patient_name="Unassigned Doctor",
            gender="F",
            age=30,
            phone_number="9876543215",
            category=self.anc,
            diagnosis="Unassigned doctor review",
            created_by=self.user,
        )
        Task.objects.create(
            case=unassigned_case,
            title="Unassigned doctor task",
            due_date=timezone.localdate(),
            created_by=self.user,
        )
        self.client.force_authenticate(doctor)

        response = self.client.get(reverse("api:case_list"), {"bucket": "today"})

        self.assertEqual(response.status_code, 200)
        uhids = {row["uhid"] for row in response.json()["results"]}
        self.assertIn("UH-API-UNASSIGNED-DOCTOR", uhids)

    def test_case_list_defaults_to_me_scope_for_non_doctor_role(self):
        mobile_user = get_user_model().objects.create_user(username="staff-mobile", password="pass")
        RoleSetting.objects.update_or_create(
            role_name="Mobile Staff",
            defaults={"case_data_scope": CaseDataScope.ASSIGNED, "can_task_edit": True},
        )
        staff_group, _ = Group.objects.get_or_create(name="Mobile Staff")
        mobile_user.groups.add(staff_group)
        assigned_case = Case.objects.create(
            uhid="UH-API-ASSIGNED-STAFF",
            first_name="Assigned",
            last_name="Staff",
            patient_name="Assigned Staff",
            gender="F",
            age=31,
            phone_number="9876543216",
            category=self.anc,
            diagnosis="Assigned staff review",
            created_by=self.user,
        )
        Task.objects.create(
            case=assigned_case,
            title="Assigned staff task",
            due_date=timezone.localdate(),
            assigned_user=mobile_user,
            created_by=self.user,
        )
        unassigned_case = Case.objects.create(
            uhid="UH-API-UNASSIGNED-STAFF",
            first_name="Unassigned",
            last_name="Staff",
            patient_name="Unassigned Staff",
            gender="F",
            age=32,
            phone_number="9876543217",
            category=self.anc,
            diagnosis="Unassigned staff review",
            created_by=self.user,
        )
        Task.objects.create(
            case=unassigned_case,
            title="Unassigned staff task",
            due_date=timezone.localdate(),
            created_by=self.user,
        )
        self.client.force_authenticate(mobile_user)

        response = self.client.get(reverse("api:case_list"), {"bucket": "today"})

        self.assertEqual(response.status_code, 200)
        uhids = {row["uhid"] for row in response.json()["results"]}
        self.assertIn("UH-API-ASSIGNED-STAFF", uhids)
        self.assertNotIn("UH-API-UNASSIGNED-STAFF", uhids)

    def test_direct_case_task_vitals_and_patient_routes_enforce_case_scope(self):
        scoped_user = get_user_model().objects.create_user(username="scoped-api-user", password="pass")
        RoleSetting.objects.create(
            role_name="Scoped API Staff",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_task_edit=True,
        )
        scoped_group = Group.objects.create(name="Scoped API Staff")
        scoped_user.groups.add(scoped_group)
        Task.objects.create(
            case=self.case,
            title="Scoped assignment",
            due_date=timezone.localdate(),
            assigned_user=scoped_user,
            created_by=self.user,
        )
        blocked_case = Case.objects.create(
            uhid="UH-API-DIRECT-BLOCKED",
            first_name="Direct",
            last_name="Blocked",
            patient_name="Direct Blocked",
            gender="F",
            age=33,
            phone_number="9876543291",
            category=self.anc,
            diagnosis="Must remain inaccessible",
            created_by=self.user,
        )
        blocked_task = Task.objects.create(
            case=blocked_case,
            title="Blocked direct task",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )
        blocked_vital = VitalEntry.objects.create(
            case=blocked_case,
            recorded_at=timezone.now(),
            pr=81,
            created_by=self.user,
            updated_by=self.user,
        )
        self.client.force_authenticate(scoped_user)

        self.assertEqual(self.client.get(reverse("api:case_detail", args=[self.case.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("api:case_detail", args=[blocked_case.pk])).status_code, 404)
        self.assertEqual(
            self.client.patch(
                reverse("api:task_detail", args=[blocked_task.pk]),
                {"notes": "forged write"},
                format="json",
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.patch(
                reverse("api:vitals_detail", args=[blocked_vital.pk]),
                {"pr": 99},
                format="json",
            ).status_code,
            404,
        )
        assigned_patient_response = self.client.post(
            reverse("api:patient_search"), {"query": "Priya"}, format="json"
        )
        blocked_patient_response = self.client.post(
            reverse("api:patient_search"), {"query": "Direct Blocked"}, format="json"
        )
        self.assertEqual(assigned_patient_response.status_code, 200)
        self.assertEqual(len(assigned_patient_response.json()["results"]), 1)
        self.assertEqual(blocked_patient_response.status_code, 200)
        self.assertEqual(blocked_patient_response.json()["results"], [])

        self.case.tasks.filter(assigned_user=scoped_user).update(assigned_user=self.user)
        self.assertEqual(self.client.get(reverse("api:case_detail", args=[self.case.pk])).status_code, 404)

    def test_direct_case_route_allows_only_current_call_queue_for_callers(self):
        caller = get_user_model().objects.create_user(username="scoped-api-caller", password="pass")
        RoleSetting.objects.create(
            role_name="Scoped API Caller",
            case_data_scope=CaseDataScope.NONE,
            can_access_call_queue=True,
            can_note_add=True,
        )
        caller_group = Group.objects.create(name="Scoped API Caller")
        caller.groups.add(caller_group)
        queue_case = Case.objects.create(
            uhid="UH-API-CALL-QUEUE",
            first_name="Queue",
            last_name="Allowed",
            patient_name="Queue Allowed",
            gender="F",
            age=34,
            phone_number="9876543292",
            category=self.anc,
            created_by=self.user,
        )
        Task.objects.create(
            case=queue_case,
            title="Call today",
            due_date=timezone.localdate(),
            created_by=self.user,
        )
        future_case = Case.objects.create(
            uhid="UH-API-CALL-FUTURE-DIRECT",
            first_name="Queue",
            last_name="Future",
            patient_name="Queue Future",
            gender="F",
            age=35,
            phone_number="9876543293",
            category=self.anc,
            created_by=self.user,
        )
        Task.objects.create(
            case=future_case,
            title="Call later",
            due_date=timezone.localdate() + timedelta(days=14),
            created_by=self.user,
        )
        self.client.force_authenticate(caller)

        self.assertEqual(self.client.get(reverse("api:case_detail", args=[queue_case.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("api:case_detail", args=[future_case.pk])).status_code, 404)

    def test_logout_returns_json_contract_for_android_client(self):
        refresh, access_claims = self._bound_refresh(self.user)
        self.client.force_authenticate(self.user, token=access_claims)

        response = self.client.post(
            reverse("api:logout"),
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Logged out.")

    def test_logout_deactivates_mobile_device_tokens(self):
        refresh, access_claims = self._bound_refresh(self.user)
        self.client.force_authenticate(self.user, token=access_claims)
        MobileDeviceToken.objects.create(user=self.user, token="active-token-1")
        MobileDeviceToken.objects.create(user=self.user, token="active-token-2")

        response = self.client.post(
            reverse("api:logout"),
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deactivated_devices"], 2)
        self.assertFalse(MobileDeviceToken.objects.filter(user=self.user, is_active=True).exists())

    def test_logout_can_deactivate_single_mobile_device_token(self):
        refresh, access_claims = self._bound_refresh(self.user)
        self.client.force_authenticate(self.user, token=access_claims)
        MobileDeviceToken.objects.create(user=self.user, token="logout-this")
        MobileDeviceToken.objects.create(user=self.user, token="keep-this")

        response = self.client.post(
            reverse("api:logout"),
            {"refresh": str(refresh), "device_token": "logout-this"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deactivated_devices"], 1)
        self.assertFalse(MobileDeviceToken.objects.get(token="logout-this").is_active)
        self.assertTrue(MobileDeviceToken.objects.get(token="keep-this").is_active)

    def test_logout_rejects_cross_account_refresh_before_any_side_effect(self):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

        other = get_user_model().objects.create_user(username="logout-other", password="pass")
        _own_refresh, own_access_claims = self._bound_refresh(self.user)
        other_refresh, _other_access_claims = self._bound_refresh(other)
        self.client.force_authenticate(self.user, token=own_access_claims)
        own_token = MobileDeviceToken.objects.create(user=self.user, token="own-active-token")
        other_token = MobileDeviceToken.objects.create(user=other, token="other-active-token")

        response = self.client.post(
            reverse("api:logout"),
            {"refresh": str(other_refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["deactivated_devices"], 0)
        own_token.refresh_from_db()
        other_token.refresh_from_db()
        self.assertTrue(own_token.is_active)
        self.assertTrue(other_token.is_active)
        self.assertFalse(BlacklistedToken.objects.filter(token__jti=other_refresh["jti"]).exists())

    def test_case_list_returns_stats_and_canva_card_fields(self):
        VitalEntry.objects.create(case=self.case, bp_systolic=138, bp_diastolic=88, pr=84, created_by=self.user)

        response = self.client.get(reverse("api:case_list"), {"bucket": "today", "assigned_to": "me"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stats"]["today"], 1)
        self.assertEqual(payload["stats"]["awaiting"], 1)
        row = payload["results"][0]
        self.assertEqual(row["uhid"], "UH-API-1")
        self.assertTrue(row["red_flag"])
        self.assertIn("category", row)
        self.assertIn("latest_vital", row)

    def test_case_list_supports_search_and_pagination_links(self):
        second_case = Case.objects.create(
            uhid="UH-API-2",
            first_name="Anita",
            last_name="Rao",
            patient_name="Anita Rao",
            gender="F",
            age=42,
            phone_number="9876543212",
            category=self.anc,
            diagnosis="Diabetes review",
            created_by=self.user,
        )
        Task.objects.create(
            case=second_case,
            title="Review glucose",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )

        page_one = self.client.get(
            reverse("api:case_list"),
            {"bucket": "today", "assigned_to": "me", "page_size": 1},
        )
        rejected_get = self.client.get(
            reverse("api:case_list"),
            {"q": "Anita"},
        )
        search = self.client.post(
            reverse("api:case_search"),
            {
                "query": "Anita",
                "bucket": "today",
                "assigned_to": "me",
                "page_size": 20,
            },
            format="json",
        )

        self.assertEqual(page_one.status_code, 200)
        self.assertIsNotNone(page_one.json()["next"])
        self.assertEqual(rejected_get.status_code, 400)
        self.assertEqual(search.status_code, 200, search.content)
        self.assertEqual(set(search.json()), {"next_cursor", "stats", "results"})
        self.assertEqual(search.json()["results"][0]["uhid"], "UH-API-2")

    def test_case_list_bucket_all_does_not_filter_by_due_bucket(self):
        future_case = Case.objects.create(
            uhid="UH-API-FUTURE",
            first_name="Future",
            last_name="Case",
            patient_name="Future Case",
            gender="F",
            age=30,
            phone_number="9876543213",
            category=self.anc,
            diagnosis="Future review",
            created_by=self.user,
        )
        Task.objects.create(
            case=future_case,
            title="Future review",
            due_date=timezone.localdate() + timedelta(days=14),
            assigned_user=self.user,
            created_by=self.user,
        )

        response = self.client.get(reverse("api:case_list"), {"bucket": "all", "assigned_to": "me"})

        self.assertEqual(response.status_code, 200)
        uhids = {row["uhid"] for row in response.json()["results"]}
        self.assertIn("UH-API-1", uhids)
        self.assertIn("UH-API-FUTURE", uhids)

    def test_case_post_search_binds_filters_and_excludes_mid_snapshot_insert(self):
        second = Case.objects.create(
            uhid="UH-SEARCH-2",
            first_name="Second",
            last_name="Search",
            patient_name="Second Search",
            phone_number="9000000002",
            category=self.anc,
            created_by=self.user,
        )
        Task.objects.create(
            case=second,
            title="Search task",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )
        url = reverse("api:case_search")
        body = {
            "query": "UH-",
            "page_size": 1,
            "bucket": "all",
            "assigned_to": "me",
            "scope_context": "",
            "category": [str(self.anc.pk)],
            "subcategory": [],
        }
        first = self.client.post(url, body, format="json")
        cursor = first.json()["next_cursor"]
        inserted = Case.objects.create(
            uhid="UH-AAA-INSERTED",
            first_name="Inserted",
            last_name="Search",
            patient_name="Inserted Search",
            phone_number="9000000003",
            category=self.anc,
            created_by=self.user,
        )
        Task.objects.create(
            case=inserted,
            title="Inserted task",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )
        second_page = self.client.post(url, {**body, "cursor": cursor}, format="json")
        mismatch = self.client.post(
            url,
            {**body, "bucket": "today", "cursor": cursor},
            format="json",
        )

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(set(first.json()), {"next_cursor", "stats", "results"})
        self.assertEqual(second_page.status_code, 200, second_page.content)
        seen = {row["id"] for row in first.json()["results"] + second_page.json()["results"]}
        self.assertNotIn(inserted.pk, seen)
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(mismatch.json()["code"], "invalid_cursor")

    def test_category_metadata_includes_subcategories_for_filter_sheet(self):
        DepartmentConfig.objects.get_or_create(name="Surgery", defaults={"auto_follow_up_days": 7})
        DepartmentConfig.objects.get_or_create(name="Medicine", defaults={"auto_follow_up_days": 7})

        response = self.client.get(reverse("api:category_metadata"))

        self.assertEqual(response.status_code, 200)
        categories = {item["name"]: item for item in response.json()["categories"]}
        self.assertIn("Surgery", categories)
        self.assertIn("Medicine", categories)
        self.assertIn(
            {"value": "GENERAL_SURGERY", "label": "General Surgery", "icon_path": "patients/icons/subcategories/general_surgery.svg"},
            categories["Surgery"]["subcategories"],
        )
        self.assertIn(
            {"value": "GENERAL_MEDICINE", "label": "General Medicine", "icon_path": "patients/icons/subcategories/general_medicine.svg"},
            categories["Medicine"]["subcategories"],
        )

    def test_case_detail_does_not_allow_cancelled_task_completion(self):
        self.awaiting_task.status = TaskStatus.CANCELLED
        self.awaiting_task.save(update_fields=["status"])

        response = self.client.get(reverse("api:case_detail", kwargs={"pk": self.case.pk}))

        self.assertEqual(response.status_code, 200)
        tasks = {item["id"]: item for item in response.json()["tasks"]}
        self.assertFalse(tasks[self.awaiting_task.id]["can_complete"])

    def test_task_complete_is_idempotent_by_client_write_id(self):
        url = reverse("api:task_complete", kwargs={"pk": self.task.pk})
        VitalEntry.objects.create(
            case=self.case,
            bp_systolic=122,
            bp_diastolic=82,
            hemoglobin="11.4",
            created_by=self.user,
        )

        first = self.client.post(url, {"client_write_id": "complete-1"}, format="json")
        second = self.client.post(url, {"client_write_id": "complete-1"}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.COMPLETED)
        self.assertEqual(MobileWriteReceipt.objects.filter(client_write_id=_idempotency_key_digest("complete-1")).count(), 1)

    def test_task_complete_rejects_archived_case_tasks(self):
        archived_case = Case.objects.create(
            uhid="UH-API-ARCHIVED",
            first_name="Archived",
            last_name="Patient",
            patient_name="Archived Patient",
            gender="F",
            age=35,
            phone_number="9876543214",
            category=self.anc,
            diagnosis="Archived review",
            is_archived=True,
            created_by=self.user,
        )
        archived_task = Task.objects.create(
            case=archived_case,
            title="Hidden follow-up",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )

        response = self.client.post(
            reverse("api:task_complete", kwargs={"pk": archived_task.pk}),
            {"client_write_id": "hidden-task-complete"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        archived_task.refresh_from_db()
        self.assertNotEqual(archived_task.status, TaskStatus.COMPLETED)
        self.assertFalse(MobileWriteReceipt.objects.filter(client_write_id=_idempotency_key_digest("hidden-task-complete")).exists())

    def test_failed_idempotent_write_replay_preserves_error_status(self):
        url = reverse("api:task_complete", kwargs={"pk": self.awaiting_task.pk})

        first = self.client.post(url, {"client_write_id": "future-anc-complete"}, format="json")
        second = self.client.post(url, {"client_write_id": "future-anc-complete"}, format="json")

        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(first.json(), second.json())
        receipt = MobileWriteReceipt.objects.get(client_write_id=_idempotency_key_digest("future-anc-complete"))
        self.assertEqual(receipt.status, MobileWriteReceipt.STATUS_FAILED)
        self.assertEqual(receipt.response_status, 400)

    def test_call_outcome_maps_mobile_values_to_existing_enum(self):
        endpoint = reverse("api:case_call_outcome", kwargs={"pk": self.case.pk})
        outcome_cases = [
            ("busy", "CALL_REJECTED"),
            ("no-answer", "NO_ANSWER"),
            ("wrong-number", "INVALID_NUMBER"),
            ("no_answer", "NO_ANSWER"),
            ("wrong_number", "INVALID_NUMBER"),
        ]

        for index, (mobile_outcome, model_outcome) in enumerate(outcome_cases, start=1):
            with self.subTest(mobile_outcome=mobile_outcome):
                response = self.client.post(
                    endpoint,
                    {
                        "outcome": mobile_outcome,
                        "note": f"Outcome {mobile_outcome}",
                        "attempted_at": timezone.now().isoformat(),
                        "client_write_id": f"call-{index}",
                    },
                    format="json",
                )

                self.assertEqual(response.status_code, 201)
                call_log = CallLog.objects.filter(case=self.case, notes=f"Outcome {mobile_outcome}").get()
                self.assertEqual(call_log.outcome, model_outcome)

    def test_call_outcome_uses_mobile_attempted_at_for_offline_sync(self):
        attempted_at = (timezone.now() - timedelta(minutes=37)).replace(microsecond=0)
        request_started_at = timezone.now()

        response = self.client.post(
            reverse("api:case_call_outcome", kwargs={"pk": self.case.pk}),
            {
                "outcome": "no-answer",
                "note": "Logged after offline sync",
                "attempted_at": attempted_at.isoformat(),
                "client_write_id": "call-offline-attempt",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        call_log = CallLog.objects.get(case=self.case, notes="Logged after offline sync")
        self.assertEqual(call_log.client_event_at, attempted_at)
        self.assertGreaterEqual(call_log.created_at, request_started_at)
        self.assertEqual(parse_datetime(response.json()["call_log"]["client_event_at"]), attempted_at)
        self.assertEqual(parse_datetime(response.json()["call_log"]["created_at"]), call_log.created_at)

    def test_call_outcome_is_idempotent_by_client_write_id(self):
        url = reverse("api:case_call_outcome", kwargs={"pk": self.case.pk})
        payload = {
            "outcome": "no-answer",
            "note": "Idempotent call",
            "attempted_at": timezone.now().isoformat(),
            "client_write_id": "call-repeat-1",
        }

        first = self.client.post(url, payload, format="json")
        second = self.client.post(url, payload, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(CallLog.objects.filter(case=self.case, notes="Idempotent call").count(), 1)
        self.assertEqual(MobileWriteReceipt.objects.filter(client_write_id=_idempotency_key_digest("call-repeat-1")).count(), 1)

    def test_vitals_create_and_thresholds_endpoint(self):
        vitals_response = self.client.post(
            reverse("api:case_vitals", kwargs={"pk": self.case.pk}),
            {"bp_systolic": 120, "bp_diastolic": 80, "pr": 82, "client_write_id": "vital-1"},
            format="json",
        )
        thresholds_response = self.client.get(reverse("api:vitals_thresholds"))

        self.assertEqual(vitals_response.status_code, 201)
        self.assertEqual(VitalEntry.objects.filter(case=self.case).count(), 1)
        self.assertEqual(thresholds_response.status_code, 200)
        self.assertIn("blood_pressure", thresholds_response.json()["metrics"])

    def test_vitals_create_accepts_red_range_values_classified_by_thresholds(self):
        response = self.client.post(
            reverse("api:case_vitals", kwargs={"pk": self.case.pk}),
            {"pr": 45, "spo2": 88, "client_write_id": "vital-red-values"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        vital = VitalEntry.objects.get(case=self.case, pr=45)
        self.assertEqual(vital.spo2, 88)

    def test_vitals_create_is_idempotent_by_client_write_id(self):
        url = reverse("api:case_vitals", kwargs={"pk": self.case.pk})
        payload = {"bp_systolic": 120, "bp_diastolic": 80, "pr": 82, "client_write_id": "vital-repeat-1"}

        first = self.client.post(url, payload, format="json")
        second = self.client.post(url, payload, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(VitalEntry.objects.filter(case=self.case, pr=82).count(), 1)
        self.assertEqual(MobileWriteReceipt.objects.filter(client_write_id=_idempotency_key_digest("vital-repeat-1")).count(), 1)

    def test_device_token_registers_or_updates(self):
        url = reverse("api:devices")

        first = self.client.post(url, {"token": "fcm-token", "app_version": "1.0"}, format="json")
        second = self.client.post(url, {"token": "fcm-token", "app_version": "1.1"}, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        device = MobileDeviceToken.objects.get(token="fcm-token")
        self.assertEqual(device.app_version, "1.1")

    def test_device_token_admin_masks_tokens(self):
        raw_token = "sensitive-fcm-token"
        device = MobileDeviceToken.objects.create(user=self.user, token=raw_token)
        model_admin = MobileDeviceTokenAdmin(MobileDeviceToken, admin.site)

        fingerprint = model_admin.token_fingerprint(device)

        self.assertNotIn("token", model_admin.search_fields)
        self.assertNotIn("token", model_admin.list_display)
        self.assertNotIn(raw_token, fingerprint)
        self.assertEqual(fingerprint, hashlib.sha256(raw_token.encode("utf-8")).hexdigest()[:12])

    @override_settings(FCM_ENABLED=True, FCM_CREDENTIALS_FILE="C:/definitely/missing/firebase.json")
    def test_push_delivery_is_disabled_when_firebase_credentials_are_missing(self):
        MobileDeviceToken.objects.create(user=self.user, token="fcm-token")
        notification = MobileNotification.objects.create(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            case=self.case,
        )

        self.assertFalse(firebase_configured())
        result = send_mobile_notification(notification)

        self.assertEqual(result["sent"], False)
        self.assertEqual(result["reason"], "fcm_not_configured")

    @override_settings(FCM_ENABLED=True)
    def test_push_delivery_failure_returns_only_sanitized_error_category(self):
        sensitive_token = "sensitive-registration-token-value"
        sensitive_path = "C:/private/firebase-service-account.json"
        MobileDeviceToken.objects.create(user=self.user, token=sensitive_token)
        notification = MobileNotification.objects.create(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            title="MEDTRACK priority update",
            case=self.case,
        )
        with (
            patch("api.push._credentials_file", return_value=sensitive_path),
            patch(
                "api.push._deliver_fcm",
                side_effect=RuntimeError(f"delivery failed for {sensitive_token} using {sensitive_path}"),
            ),
        ):
            result = send_mobile_notification(notification)

        self.assertEqual(
            result,
            {
                "sent": False,
                "reason": "fcm_delivery_failed",
                "error_category": "unknown",
            },
        )
        self.assertNotIn(sensitive_token, str(result))
        self.assertNotIn(sensitive_path, str(result))

    def test_push_delivery_deactivates_permanently_failed_tokens(self):
        stale_device = MobileDeviceToken.objects.create(user=self.user, token="stale-token")
        transient_device = MobileDeviceToken.objects.create(user=self.user, token="transient-token")
        active_device = MobileDeviceToken.objects.create(user=self.user, token="active-token")

        inactive_count = _deactivate_permanently_failed_tokens(
            ["stale-token", "transient-token", "active-token"],
            [
                FakeFirebaseSendResponse(FakeFirebaseError("registration-token-not-registered")),
                FakeFirebaseSendResponse(FakeFirebaseError("temporary unavailable")),
                FakeFirebaseSendResponse(None),
            ],
        )

        self.assertEqual(inactive_count, 1)
        stale_device.refresh_from_db()
        transient_device.refresh_from_db()
        active_device.refresh_from_db()
        self.assertFalse(stale_device.is_active)
        self.assertTrue(transient_device.is_active)
        self.assertTrue(active_device.is_active)

    def test_every_push_payload_path_is_data_only_with_opaque_event_id(self):
        sensitive_values = [
            "Priya Sharma",
            "9876543210",
            "Severe hypertension",
            "Collect private lab report",
            "CASE-ID-SENSITIVE-8472",
        ]
        expected_priorities = {
            MobileNotificationType.ASSIGNMENT: "high",
            MobileNotificationType.RED_FLAG: "high",
            MobileNotificationType.OVERDUE: "normal",
        }
        with self.assertRaises(IntegrityError), transaction.atomic():
            MobileNotification.objects.bulk_create(
                [
                    MobileNotification(
                        user=self.user,
                        notification_type=MobileNotificationType.RED_FLAG,
                        title="Patient Priya Sharma",
                        body="Sensitive clinical body",
                        case=self.case,
                    )
                ]
            )
        for notification_type, expected_priority in expected_priorities.items():
            with self.subTest(notification_type=notification_type):
                with self.assertRaises(ValidationError):
                    MobileNotification.objects.create(
                        user=self.user,
                        notification_type=notification_type,
                        title=sensitive_values[0],
                        body=f"{sensitive_values[2]}: {sensitive_values[3]}",
                        case=self.case,
                    )
                notification = MobileNotification.objects.create(
                    user=self.user,
                    notification_type=notification_type,
                    case=self.case,
                )

                message = _build_multicast_message(
                    FakeFirebaseMessaging,
                    notification,
                    ["safe-token"],
                )
                transmitted = str(message.data)

                self.assertEqual(message.tokens, ["safe-token"])
                self.assertIsNone(message.notification)
                self.assertEqual(message.data, {"event_id": str(notification.event_id)})
                self.assertEqual(message.android.priority, expected_priority)
                self.assertIsNone(message.android.notification)
                for sensitive_value in sensitive_values:
                    self.assertNotIn(sensitive_value, transmitted)

    @override_settings(FCM_ENABLED=True)
    def test_push_excludes_revoked_and_device_switched_tokens(self):
        switched_token = "device-switched-token"
        revoked_token = "revoked-token"
        active_token = "current-active-token"
        MobileDeviceToken.objects.create(user=self.user, token=switched_token)
        MobileDeviceToken.objects.create(user=self.user, token=revoked_token, is_active=False)
        MobileDeviceToken.objects.create(user=self.user, token=active_token)
        new_owner = get_user_model().objects.create_user(username="device-new-owner", password="pass")
        new_owner_client = APIClient()
        new_owner_client.force_authenticate(new_owner)
        switched = new_owner_client.post(
            reverse("api:devices"),
            {"token": switched_token, "device_label": "replacement account"},
            format="json",
        )
        notification = MobileNotification.objects.create(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            case=self.case,
        )
        delivery_response = FakeFirebaseBatchResponse(success_count=1, failure_count=0)

        with (
            patch("api.push._credentials_file", return_value="C:/test/firebase.json"),
            patch("api.push._deliver_fcm", return_value=delivery_response) as deliver,
        ):
            result = send_mobile_notification(notification)

        self.assertEqual(switched.status_code, 200)
        self.assertTrue(result["sent"])
        self.assertEqual(deliver.call_args.args[1], [active_token])
        self.assertNotIn(switched_token, deliver.call_args.args[1])
        self.assertNotIn(revoked_token, deliver.call_args.args[1])

    @override_settings(FCM_ENABLED=True)
    def test_opaque_event_send_fails_closed_after_role_scope_revocation(self):
        role = RoleSetting.objects.create(
            role_name="Push Scope Revocation",
            case_data_scope=CaseDataScope.ASSIGNED,
        )
        group = Group.objects.create(name=role.role_name)
        scoped_user = get_user_model().objects.create_user(username="push-scope-user", password="pass")
        scoped_user.groups.add(group)
        scoped_task = Task.objects.create(
            case=self.case,
            title="Scope-sensitive task",
            due_date=timezone.localdate(),
            assigned_user=scoped_user,
            created_by=self.user,
        )
        MobileDeviceToken.objects.create(user=scoped_user, token="scope-revoked-token")
        notification = MobileNotification.objects.get(user=scoped_user, task=scoped_task)
        RoleSetting.objects.filter(pk=role.pk).update(case_data_scope=CaseDataScope.NONE)

        with (
            patch("api.push._credentials_file", return_value="C:/test/firebase.json"),
            patch("api.push._deliver_fcm") as deliver,
        ):
            result = send_mobile_notification(notification)

        self.assertEqual(result, {"sent": False, "reason": "authorization_revoked"})
        self.assertFalse(MobileNotification.objects.filter(pk=notification.pk).exists())
        deliver.assert_not_called()

    def test_task_assignment_creates_deduped_mobile_notification(self):
        task = Task.objects.create(
            case=self.case,
            title="Collect labs",
            due_date=timezone.localdate() + timedelta(days=1),
            assigned_user=self.user,
            created_by=self.user,
        )
        task.notes = "Same assignee update"
        task.save(update_fields=["notes", "updated_at"])

        notifications = MobileNotification.objects.filter(
            user=self.user,
            notification_type=MobileNotificationType.ASSIGNMENT,
            task=task,
        )
        self.assertEqual(notifications.count(), 1)
        notification = notifications.get()
        serialized = _serialize_notification(notification)
        self.assertEqual(set(serialized["payload"]), {"event_id", "type", "channel"})
        self.assertNotIn(self.case.phone_number, str(serialized["payload"]))

    def test_task_reassignment_notifies_new_assignee(self):
        new_user = get_user_model().objects.create_user(username="new-assignee", password="pass")
        role = RoleSetting.objects.create(
            role_name="New Assignee Mobile",
            case_data_scope=CaseDataScope.ASSIGNED,
        )
        group = Group.objects.create(name=role.role_name)
        new_user.groups.add(group)
        self.task.assigned_user = new_user
        self.task.save(update_fields=["assigned_user", "updated_at"])

        notification = MobileNotification.objects.get(
            user=new_user,
            notification_type=MobileNotificationType.ASSIGNMENT,
            task=self.task,
        )
        self.assertEqual(_serialize_notification(notification)["payload"]["type"], MobileNotificationType.ASSIGNMENT)

    def test_red_flag_signal_notifies_case_assigned_users_once(self):
        case = Case.objects.create(
            uhid="UH-API-RED",
            first_name="Meena",
            last_name="Rao",
            patient_name="Meena Rao",
            gender="F",
            age=31,
            phone_number="9876543211",
            category=self.anc,
            diagnosis="Pregnancy",
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Review",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )
        MobileNotification.objects.all().delete()

        case.high_risk = True
        case.save(update_fields=["high_risk"])
        case.diagnosis = "Pregnancy review"
        case.save(update_fields=["diagnosis", "updated_at"])

        notifications = MobileNotification.objects.filter(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            case=case,
        )
        self.assertEqual(notifications.count(), 1)
        serialized = _serialize_notification(notifications.get())
        self.assertEqual(serialized["payload"]["channel"], "red_flags")
        self.assertNotIn("9876543211", str(serialized["payload"]))

    def test_notification_event_predicates_replace_risk_change_and_revoke_resolved_or_rescheduled(self):
        state, _ = MobileNotificationState.objects.get_or_create(user=self.user)
        before_epoch = state.epoch

        self.case.anc_high_risk_reasons = ["PREVIOUS_COMPLICATION"]
        self.case.save(update_fields=["anc_high_risk_reasons", "updated_at"])
        original = MobileNotification.objects.get(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            case=self.case,
        )
        self.case.anc_high_risk_reasons = ["GESTATIONAL_DIABETES"]
        self.case.save(update_fields=["anc_high_risk_reasons", "updated_at"])
        replacement = MobileNotification.objects.get(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            case=self.case,
        )
        state.refresh_from_db()
        self.assertNotEqual(replacement.event_id, original.event_id)
        self.assertNotEqual(state.epoch, before_epoch)

        self.case.high_risk = False
        self.case.anc_high_risk_reasons = []
        self.case.ncd_flags = []
        self.case.save(update_fields=["high_risk", "anc_high_risk_reasons", "ncd_flags", "updated_at"])
        self.assertFalse(MobileNotification.objects.filter(pk=replacement.pk).exists())

        overdue = Task.objects.create(
            case=self.case,
            title="Predicate overdue",
            due_date=timezone.localdate() - timedelta(days=1),
            assigned_user=self.user,
            created_by=self.user,
        )
        call_command("send_mobile_overdue_notifications", stdout=StringIO())
        overdue_event = MobileNotification.objects.get(
            user=self.user,
            task=overdue,
            notification_type=MobileNotificationType.OVERDUE,
        )
        overdue.due_date = timezone.localdate() + timedelta(days=2)
        overdue.save(update_fields=["due_date", "updated_at"])
        self.assertFalse(MobileNotification.objects.filter(pk=overdue_event.pk).exists())

    def test_overdue_management_command_creates_deduped_notifications(self):
        overdue_task = Task.objects.create(
            case=self.case,
            title="Missed review",
            due_date=timezone.localdate() - timedelta(days=2),
            status=TaskStatus.SCHEDULED,
            assigned_user=self.user,
            created_by=self.user,
        )
        MobileNotification.objects.all().delete()

        output = StringIO()
        call_command("send_mobile_overdue_notifications", stdout=output)
        call_command("send_mobile_overdue_notifications", stdout=StringIO())

        notifications = MobileNotification.objects.filter(
            user=self.user,
            notification_type=MobileNotificationType.OVERDUE,
            task=overdue_task,
        )
        self.assertEqual(notifications.count(), 1)
        self.assertIn("Processed", output.getvalue())
        self.assertEqual(set(_serialize_notification(notifications.get())["payload"]), {"event_id", "type", "channel"})

    def test_notification_read_marks_only_current_users_notification(self):
        other_user = get_user_model().objects.create_user(username="other-user", password="pass")
        notification = MobileNotification.objects.create(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            case=self.case,
        )
        other_notification = MobileNotification.objects.create(
            user=other_user,
            notification_type=MobileNotificationType.RED_FLAG,
            case=self.case,
        )

        response = self.client.post(reverse("api:notification_read", kwargs={"pk": notification.pk}))
        forbidden = self.client.post(reverse("api:notification_read", kwargs={"pk": other_notification.pk}))

        self.assertEqual(response.status_code, 200)
        notification.refresh_from_db()
        other_notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.assertIsNone(other_notification.read_at)
        self.assertEqual(forbidden.status_code, 404)

    def test_notification_list_read_and_send_reauthorize_current_assignment(self):
        role = RoleSetting.objects.create(
            role_name="Notification Scoped",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_task_edit=True,
        )
        group = Group.objects.create(name=role.role_name)
        scoped_user = get_user_model().objects.create_user(username="notification-scoped", password="pass")
        scoped_user.groups.add(group)
        scoped_task = Task.objects.create(
            case=self.case,
            title="Scoped notification",
            due_date=timezone.localdate(),
            assigned_user=scoped_user,
            created_by=self.user,
        )
        client = APIClient()
        client.force_authenticate(scoped_user)
        original = MobileNotification.objects.get(user=scoped_user, task=scoped_task)

        # Bypass signals to simulate a stale row left by an external/concurrent change.
        Task.objects.filter(pk=scoped_task.pk).update(assigned_user=self.user)

        listed = client.get(reverse("api:notifications"))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["results"], [])
        self.assertFalse(MobileNotification.objects.filter(pk=original.pk).exists())

        stale_read = MobileNotification.objects.create(
            user=scoped_user,
            notification_type=MobileNotificationType.ASSIGNMENT,
            title="MEDTRACK assignment",
            case=self.case,
            task=scoped_task,
        )
        read_response = client.post(reverse("api:notification_read", args=[stale_read.pk]))
        self.assertEqual(read_response.status_code, 404)
        self.assertFalse(MobileNotification.objects.filter(pk=stale_read.pk).exists())

        stale_send = MobileNotification.objects.create(
            user=scoped_user,
            notification_type=MobileNotificationType.ASSIGNMENT,
            title="MEDTRACK assignment",
            case=self.case,
            task=scoped_task,
        )
        send_result = send_mobile_notification(stale_send)
        self.assertEqual(send_result, {"sent": False, "reason": "authorization_revoked"})
        self.assertFalse(MobileNotification.objects.filter(pk=stale_send.pk).exists())

    def test_notification_cursor_snapshot_is_stable_when_new_rows_are_inserted(self):
        anchor = timezone.now().replace(microsecond=0)
        original_ids = []
        for offset in range(5):
            notification = MobileNotification.objects.create(
                user=self.user,
                notification_type=MobileNotificationType.RED_FLAG,
                title="MEDTRACK priority update",
                case=self.case,
            )
            MobileNotification.objects.filter(pk=notification.pk).update(
                created_at=anchor - timedelta(minutes=offset)
            )
            original_ids.append(notification.pk)

        url = reverse("api:notifications")
        first = self.client.get(url, {"page_size": 2})
        cursor = first.json()["next_cursor"]
        inserted = MobileNotification.objects.create(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            title="MEDTRACK priority update",
            case=self.case,
        )
        MobileNotification.objects.filter(pk=inserted.pk).update(
            created_at=anchor + timedelta(minutes=1)
        )

        seen_ids = [row["id"] for row in first.json()["results"]]
        while cursor:
            response = self.client.get(url, {"page_size": 2, "cursor": cursor})
            self.assertEqual(response.status_code, 200, response.content)
            seen_ids.extend(row["id"] for row in response.json()["results"])
            cursor = response.json()["next_cursor"]

        fresh = self.client.get(url, {"page_size": 2})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(
            set(first.json()),
            {"dataset_epoch", "next_cursor", "results"},
        )
        self.assertEqual(len(seen_ids), len(set(seen_ids)))
        self.assertEqual(set(seen_ids), set(original_ids))
        self.assertNotIn(inserted.pk, seen_ids)
        self.assertEqual(fresh.json()["results"][0]["id"], inserted.pk)

    def test_notification_cursor_rejects_filter_changes_and_legacy_pages(self):
        for _ in range(2):
            MobileNotification.objects.create(
                user=self.user,
                notification_type=MobileNotificationType.RED_FLAG,
                title="MEDTRACK priority update",
                case=self.case,
            )
        url = reverse("api:notifications")
        first = self.client.get(url, {"type": "red_flag", "page_size": 1})
        cursor = first.json()["next_cursor"]

        type_mismatch = self.client.get(
            url,
            {"type": "overdue", "page_size": 1, "cursor": cursor},
        )
        unread_mismatch = self.client.get(
            url,
            {"type": "red_flag", "unread_only": "true", "page_size": 1, "cursor": cursor},
        )
        page_size_mismatch = self.client.get(
            url,
            {"type": "red_flag", "page_size": 2, "cursor": cursor},
        )
        legacy_page = self.client.get(url, {"page": 2})

        self.assertIsNotNone(cursor)
        self.assertEqual(type_mismatch.status_code, 400)
        self.assertEqual(type_mismatch.json()["code"], "invalid_cursor")
        self.assertEqual(unread_mismatch.status_code, 400)
        self.assertEqual(unread_mismatch.json()["code"], "invalid_cursor")
        self.assertEqual(page_size_mismatch.status_code, 400)
        self.assertEqual(page_size_mismatch.json()["code"], "invalid_cursor")
        self.assertEqual(legacy_page.status_code, 400)
        self.assertEqual(legacy_page.json()["code"], "page_not_supported")

    def test_notification_cursor_reauthorizes_and_purges_revocation_between_pages(self):
        role = RoleSetting.objects.create(
            role_name="Notification Cursor Scoped",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_task_edit=True,
        )
        group = Group.objects.create(name=role.role_name)
        scoped_user = get_user_model().objects.create_user(
            username="notification-cursor-scoped",
            password="pass",
        )
        scoped_user.groups.add(group)
        tasks = [
            Task.objects.create(
                case=self.case,
                title=f"Cursor task {index}",
                due_date=timezone.localdate(),
                assigned_user=scoped_user,
                created_by=self.user,
            )
            for index in range(2)
        ]
        client = APIClient()
        client.force_authenticate(scoped_user)
        url = reverse("api:notifications")
        first = client.get(url, {"page_size": 1})
        cursor = first.json()["next_cursor"]
        first_task_id = first.json()["results"][0]["task_id"]
        revoked_task = next(task for task in tasks if task.pk != first_task_id)
        revoked_notification_id = MobileNotification.objects.get(
            user=scoped_user,
            task=revoked_task,
        ).pk

        Task.objects.filter(pk=revoked_task.pk).update(assigned_user=self.user)
        continued = client.get(url, {"page_size": 1, "cursor": cursor})

        self.assertIsNotNone(cursor)
        self.assertEqual(continued.status_code, 400, continued.content)
        self.assertEqual(continued.json()["code"], "invalid_cursor")
        self.assertFalse(MobileNotification.objects.filter(pk=revoked_notification_id).exists())

    def test_notification_retention_cleanup_is_bounded_and_expired_rows_are_hidden(self):
        expired = [
            MobileNotification.objects.create(
                user=self.user,
                notification_type=MobileNotificationType.RED_FLAG,
                title="MEDTRACK priority update",
                case=self.case,
            )
            for _ in range(3)
        ]
        MobileNotification.objects.filter(pk__in=[row.pk for row in expired]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        deleted = purge_expired_mobile_notifications(limit=2)
        response = self.client.get(reverse("api:notifications"))

        self.assertEqual(deleted, 2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        self.assertFalse(MobileNotification.objects.filter(pk__in=[row.pk for row in expired]).exists())

    def test_task_terminal_status_purges_notifications_and_reopen_emits_fresh_event(self):
        task = Task.objects.create(
            case=self.case,
            title="Terminal notification lifecycle",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )
        original_event_id = MobileNotification.objects.get(task=task).event_id

        task.status = TaskStatus.COMPLETED
        task.save(update_fields=["status", "updated_at"])
        self.assertFalse(MobileNotification.objects.filter(task=task).exists())

        task.status = TaskStatus.SCHEDULED
        task.save(update_fields=["status", "updated_at"])
        reopened = MobileNotification.objects.get(task=task)
        self.assertNotEqual(reopened.event_id, original_event_id)

        task.status = TaskStatus.CANCELLED
        task.save(update_fields=["status", "updated_at"])
        self.assertFalse(MobileNotification.objects.filter(task=task).exists())

    def test_idempotency_key_reuse_with_different_payload_returns_409(self):
        url = reverse("api:task_complete", kwargs={"pk": self.task.pk})
        first = self.client.post(url, {"client_write_id": "binding-payload"}, format="json")
        mismatch = self.client.post(
            url,
            {"client_write_id": "binding-payload", "unexpected": "different"},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(mismatch.json()["code"], "idempotency_mismatch")

    def test_idempotency_key_reuse_across_targets_returns_409(self):
        second_task = Task.objects.create(
            case=self.case,
            title="Second binding target",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )
        first = self.client.post(
            reverse("api:task_complete", args=[self.task.pk]),
            {"client_write_id": "binding-target"},
            format="json",
        )
        mismatch = self.client.post(
            reverse("api:task_complete", args=[second_task.pk]),
            {"client_write_id": "binding-target"},
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(mismatch.status_code, 409)
        second_task.refresh_from_db()
        self.assertNotEqual(second_task.status, TaskStatus.COMPLETED)

    def test_idempotency_replay_is_bound_to_authorization_fingerprint(self):
        role = RoleSetting.objects.create(
            role_name="Receipt Role",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_task_edit=True,
        )
        group = Group.objects.create(name=role.role_name)
        scoped_user = get_user_model().objects.create_user(username="receipt-user", password="pass")
        scoped_user.groups.add(group)
        scoped_task = Task.objects.create(
            case=self.case,
            title="Scoped receipt",
            due_date=timezone.localdate(),
            assigned_user=scoped_user,
            created_by=self.user,
        )
        client = APIClient()
        client.force_authenticate(scoped_user)
        url = reverse("api:task_complete", args=[scoped_task.pk])
        first = client.post(url, {"client_write_id": "binding-auth"}, format="json")

        before_scope_change = _authorization_hash(scoped_user)
        RoleSetting.objects.filter(pk=role.pk).update(can_intake_patient_lookup=True)
        after_scope_change = _authorization_hash(scoped_user)
        mismatch = client.post(url, {"client_write_id": "binding-auth"}, format="json")
        security_state = UserSecurityState.objects.get(user=scoped_user)
        security_state.auth_version += 1
        security_state.save(update_fields=["auth_version", "updated_at"])
        after_auth_version_change = _authorization_hash(scoped_user)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(mismatch.status_code, 409)
        self.assertNotEqual(before_scope_change, after_scope_change)
        self.assertNotEqual(after_scope_change, after_auth_version_change)

    def test_idempotency_replay_is_bound_to_dataset_epoch(self):
        url = reverse("api:case_vitals", kwargs={"pk": self.case.pk})
        payload = {"pr": 80, "client_write_id": "binding-epoch"}
        first = self.client.post(url, payload, format="json")
        MobileDatasetState.objects.filter(pk=1).update(epoch=uuid.uuid4())
        mismatch = self.client.post(url, payload, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(VitalEntry.objects.filter(case=self.case, pr=80).count(), 1)

    def test_idempotency_receipt_is_expiring_and_contains_no_response_phi(self):
        response = self.client.post(
            reverse("api:case_vitals", kwargs={"pk": self.case.pk}),
            {"pr": 81, "client_write_id": "minimal-receipt"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        receipt = MobileWriteReceipt.objects.get(client_write_id=_idempotency_key_digest("minimal-receipt"))
        self.assertGreater(receipt.expires_at, timezone.now())
        self.assertEqual(set(receipt.response_metadata), {"message"})
        self.assertNotIn(self.case.full_name, str(receipt.response_metadata))
        self.assertEqual(len(receipt.payload_hash), 64)
        self.assertEqual(len(receipt.authorization_hash), 64)
        MobileWriteReceipt.objects.filter(pk=receipt.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        follow_up = self.client.post(
            reverse("api:case_vitals", kwargs={"pk": self.case.pk}),
            {"pr": 82, "client_write_id": "cleanup-trigger"},
            format="json",
        )

        self.assertEqual(follow_up.status_code, 201)
        self.assertFalse(MobileWriteReceipt.objects.filter(pk=receipt.pk).exists())

    def test_reassignment_revokes_notification_and_device_after_access_loss(self):
        role = RoleSetting.objects.create(
            role_name="Assigned Mobile",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_task_edit=True,
        )
        group = Group.objects.create(name=role.role_name)
        assignee = get_user_model().objects.create_user(username="old-mobile-assignee", password="pass")
        assignee.groups.add(group)
        assigned_task = Task.objects.create(
            case=self.case,
            title="Revoke assignment",
            due_date=timezone.localdate(),
            assigned_user=assignee,
            created_by=self.user,
        )
        token = MobileDeviceToken.objects.create(user=assignee, token="old-assignee-token")
        self.assertTrue(MobileNotification.objects.filter(user=assignee, task=assigned_task).exists())

        assigned_task.assigned_user = self.user
        assigned_task.save(update_fields=["assigned_user", "updated_at"])

        token.refresh_from_db()
        self.assertFalse(token.is_active)
        self.assertFalse(MobileNotification.objects.filter(user=assignee, case=self.case).exists())

    def test_role_change_revokes_device_and_receipts(self):
        role = RoleSetting.objects.create(
            role_name="Mutable Mobile",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_task_edit=True,
        )
        group = Group.objects.create(name=role.role_name)
        mobile_user = get_user_model().objects.create_user(username="mutable-mobile", password="pass")
        mobile_user.groups.add(group)
        mobile_task = Task.objects.create(
            case=self.case,
            title="Role-bound write",
            due_date=timezone.localdate(),
            assigned_user=mobile_user,
            created_by=self.user,
        )
        token = MobileDeviceToken.objects.create(user=mobile_user, token="role-token")
        client = APIClient()
        client.force_authenticate(mobile_user)
        self.assertEqual(
            client.post(
                reverse("api:task_complete", args=[mobile_task.pk]),
                {"client_write_id": "role-receipt"},
                format="json",
            ).status_code,
            200,
        )

        role.can_note_add = True
        role.save(update_fields=["can_note_add"])

        token.refresh_from_db()
        self.assertFalse(token.is_active)
        self.assertFalse(MobileWriteReceipt.objects.filter(user=mobile_user).exists())

    def test_case_delete_purges_linked_notification_and_receipt(self):
        self.client.post(
            reverse("api:task_complete", args=[self.task.pk]),
            {"client_write_id": "delete-receipt"},
            format="json",
        )
        MobileNotification.objects.create(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            title="MEDTRACK priority update",
            case=self.case,
        )

        self.case.delete()

        self.assertFalse(MobileNotification.objects.exists())
        self.assertFalse(MobileWriteReceipt.objects.filter(client_write_id=_idempotency_key_digest("delete-receipt")).exists())

    def test_dataset_invalidation_advances_epoch_and_revokes_all_mobile_state(self):
        MobileDeviceToken.objects.create(user=self.user, token="dataset-token")
        MobileNotification.objects.create(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            title="MEDTRACK priority update",
            case=self.case,
        )
        self.client.post(
            reverse("api:case_vitals", args=[self.case.pk]),
            {"pr": 83, "client_write_id": "dataset-receipt"},
            format="json",
        )
        before = MobileDatasetState.objects.get(pk=1).epoch

        with transaction.atomic():
            after = invalidate_mobile_dataset()

        self.assertNotEqual(before, after)
        self.assertFalse(MobileNotification.objects.exists())
        self.assertFalse(MobileWriteReceipt.objects.exists())
        self.assertFalse(MobileDeviceToken.objects.filter(is_active=True).exists())

    def test_patient_search_is_post_only_minimal_and_never_places_phi_in_url(self):
        search_url = reverse("api:patient_search")
        sentinel = "Priya-Sensitive-Search"
        rejected_get = self.client.get(search_url, {"q": sentinel})
        short = self.client.post(search_url, {"query": "Pr"}, format="json")
        found = self.client.post(search_url, {"query": "Pri"}, format="json")
        phone = self.client.post(search_url, {"query": "987-654-3210"}, format="json")

        self.assertEqual(rejected_get.status_code, 405)
        self.assertNotIn(sentinel, rejected_get.content.decode("utf-8"))
        self.assertEqual(short.status_code, 400)
        self.assertEqual(short.json()["code"], "invalid_search_request")
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.wsgi_request.get_full_path(), search_url)
        self.assertEqual(set(found.json()), {"next_cursor", "results"})
        self.assertEqual(set(found.json()["results"][0]), {"id", "uhid", "name"})
        self.assertEqual(phone.json()["results"][0]["uhid"], self.case.uhid)

    def test_patient_search_cursor_is_stable_and_bound_to_normalized_query(self):
        second_case = Case.objects.create(
            uhid="UH-API-2",
            first_name="Second",
            last_name="Patient",
            patient_name="Second Patient",
            phone_number="9876543212",
            category=self.anc,
            created_by=self.user,
        )
        search_url = reverse("api:patient_search")

        first = self.client.post(
            search_url,
            {"query": "UH-", "page_size": 1},
            format="json",
        )
        cursor = first.json()["next_cursor"]
        inserted = Case.objects.create(
            uhid="UH-AAAA-INSERTED",
            first_name="Inserted",
            last_name="Patient",
            patient_name="Inserted Patient",
            phone_number="9876543299",
            category=self.anc,
            created_by=self.user,
        )
        second = self.client.post(
            search_url,
            {"query": "uh-", "page_size": 1, "cursor": cursor},
            format="json",
        )
        mismatch = self.client.post(
            search_url,
            {"query": "Pri", "page_size": 1, "cursor": cursor},
            format="json",
        )
        page_size_mismatch = self.client.post(
            search_url,
            {"query": "UH-", "page_size": 2, "cursor": cursor},
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertIsNotNone(cursor)
        self.assertEqual(first.json()["results"][0]["uhid"], self.case.uhid)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["results"][0]["uhid"], second_case.uhid)
        self.assertIsNone(second.json()["next_cursor"])
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(mismatch.json()["code"], "invalid_cursor")
        self.assertEqual(page_size_mismatch.status_code, 400)
        self.assertNotEqual(second.json()["results"][0]["id"], inserted.patient_id)
        self.assertNotIn("UH-API", cursor)

    def test_patient_search_shared_throttle_audits_throttled_attempt(self):
        url = reverse("api:patient_search")
        responses = [self.client.post(url, {"query": "Pri"}, format="json") for _ in range(31)]

        self.assertTrue(all(response.status_code == 200 for response in responses[:30]))
        self.assertEqual(responses[30].status_code, 429)
        events = AuditEvent.objects.filter(action="patient.search_attempt")
        self.assertEqual(events.count(), 31)
        throttled = events.filter(metadata__search_class="throttled").get()
        self.assertEqual(throttled.outcome, AuditEvent.Outcome.DENIED)
        self.assertNotIn("Pri", str(throttled.metadata))

    def test_patient_search_allows_intake_only_scope_and_phone_is_exact_only(self):
        role = RoleSetting.objects.create(
            role_name="Intake Lookup Only",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_case_create=True,
            can_intake_patient_lookup=True,
        )
        group = Group.objects.create(name=role.role_name)
        intake_user = get_user_model().objects.create_user(username="intake-only-api", password="pass")
        intake_user.groups.add(group)
        self.case.patient.created_by = intake_user
        self.case.patient.save(update_fields=["created_by"])
        misleading = Case.objects.create(
            uhid=self.case.phone_number,
            first_name="Numeric",
            last_name="Identifier",
            patient_name="Numeric Identifier",
            phone_number="9000000000",
            category=self.anc,
            created_by=self.user,
        )
        client = APIClient()
        client.force_authenticate(intake_user)

        response = client.post(
            reverse("api:patient_search"),
            {"query": self.case.phone_number},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        result_ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(self.case.patient_id, result_ids)
        self.assertNotIn(misleading.patient_id, result_ids)

    def test_patient_search_audit_is_phi_safe_and_captures_request_context(self):
        credential = StaffDeviceCredential.objects.create(
            user=self.user,
            device_label="Search audit device",
            credential_id="search-audit-credential",
            public_key="test-public-key",
        )
        session = self.client.session
        session["medtrack_device_credential_id"] = credential.pk
        session.save()
        search_url = reverse("api:patient_search")

        found = self.client.post(
            search_url,
            {"query": "Priya"},
            format="json",
            HTTP_X_REQUEST_ID="patient-search-audit-request",
        )
        rejected = self.client.post(
            search_url,
            {"query": "Pr"},
            format="json",
            HTTP_X_REQUEST_ID="patient-search-denied-request",
        )

        events = AuditEvent.objects.filter(action="patient.search_attempt").order_by("occurred_at", "id")
        success_event, denied_event = list(events)
        self.assertEqual(found.status_code, 200)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(success_event.actor_user_id, self.user.pk)
        self.assertEqual(success_event.source, "api")
        self.assertEqual(success_event.request_id, "patient-search-audit-request")
        self.assertTrue(success_event.session_key_hash)
        self.assertTrue(success_event.source_ip_hash)
        self.assertEqual(success_event.device_credential_id, credential.pk)
        self.assertEqual(success_event.outcome, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(
            success_event.metadata,
            {
                "search_class": "name_or_uhid_prefix",
                "normalized_length": 5,
                "result_count": 1,
                "scope": {
                    "case_data_scope": CaseDataScope.ALL,
                    "call_queue": True,
                    "intake_patient_lookup": True,
                },
            },
        )
        self.assertEqual(denied_event.outcome, AuditEvent.Outcome.DENIED)
        self.assertEqual(denied_event.request_id, "patient-search-denied-request")
        self.assertEqual(denied_event.metadata["normalized_length"], 2)
        audit_material = f"{success_event.metadata} {denied_event.metadata}"
        self.assertNotIn("Priya", audit_material)
        self.assertNotIn(self.case.uhid, audit_material)
        self.assertNotIn(self.case.phone_number, audit_material)

    def test_client_event_timestamps_are_bounded(self):
        future = timezone.now() + timedelta(minutes=6)
        old = timezone.now() - timedelta(days=31)

        future_call = self.client.post(
            reverse("api:case_call_outcome", args=[self.case.pk]),
            {"outcome": "no-answer", "attempted_at": future.isoformat()},
            format="json",
        )
        old_vital = self.client.post(
            reverse("api:case_vitals", args=[self.case.pk]),
            {"pr": 80, "recorded_at": old.isoformat()},
            format="json",
        )

        self.assertEqual(future_call.status_code, 400)
        self.assertEqual(old_vital.status_code, 400)

    def test_identical_call_replay_precedes_rolling_timestamp_validation(self):
        base_now = timezone.now().replace(microsecond=0)
        payload = {
            "outcome": "no-answer",
            "attempted_at": (base_now - timedelta(days=29)).isoformat(),
            "client_write_id": "rolling-window-replay",
        }
        url = reverse("api:case_call_outcome", args=[self.case.pk])
        first = self.client.post(url, payload, format="json")
        with patch("api.serializers.timezone.now", return_value=base_now + timedelta(days=2)):
            replay = self.client.post(url, payload, format="json")

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(replay.status_code, 201, replay.content)
        self.assertEqual(first.json()["call_log"]["id"], replay.json()["call_log"]["id"])
        self.assertEqual(CallLog.objects.filter(case=self.case).count(), 1)

    def test_generated_schema_covers_every_mobile_endpoint_and_surgery_done(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        expected_paths = {
            "/api/me/",
            "/api/cases/",
            "/api/cases/search/",
            "/api/cases/{id}/",
            "/api/cases/{id}/edit-form/",
            "/api/patients/",
            "/api/notifications/",
            "/api/notifications/{id}/read/",
        }

        self.assertTrue(expected_paths.issubset(schema["paths"]))
        operation_ids = [
            operation["operationId"]
            for path_item in schema["paths"].values()
            for method, operation in path_item.items()
            if method in {"get", "post", "patch", "put", "delete"}
        ]
        self.assertEqual(len(operation_ids), len(set(operation_ids)))
        case_create = schema["components"]["schemas"]["CaseCreateRequest"]
        case_patch = schema["components"]["schemas"]["CasePatchRequest"]
        self.assertIn("surgery_done", case_create["properties"])
        self.assertIn("surgery_done", case_patch["properties"])
        self.assertTrue({"base_updated_at", "base_values"}.issubset(case_patch["required"]))
        editable_case = schema["components"]["schemas"]["EditableCaseContract"]
        self.assertIn("surgery_done", editable_case["properties"])
        self.assertNotIn("client_write_id", editable_case["properties"])
        self.assertEqual(
            set(editable_case["properties"]),
            set(editable_case["required"]),
        )
        patient_path = schema["paths"]["/api/patients/"]
        self.assertIn("post", patient_path)
        self.assertNotIn("get", patient_path)
        patient_request = schema["components"]["schemas"]["PatientSearchRequest"]
        self.assertEqual(
            set(patient_request["properties"]),
            {"query", "page_size", "cursor"},
        )
        self.assertEqual(patient_request["required"], ["query"])
        patient_response = schema["components"]["schemas"]["PatientSearchResponse"]
        self.assertEqual(set(patient_response["properties"]), {"next_cursor", "results"})
        notification_parameters = {
            parameter["name"] for parameter in schema["paths"]["/api/notifications/"]["get"]["parameters"]
        }
        self.assertEqual(
            notification_parameters,
            {"cursor", "page_size", "type", "unread_only"},
        )
        notification_response = schema["components"]["schemas"]["NotificationsResponse"]
        self.assertEqual(
            set(notification_response["properties"]),
            {"dataset_epoch", "next_cursor", "results"},
        )
        me_response = schema["components"]["schemas"]["MeResponse"]
        self.assertIn("data_scope", me_response["properties"])
        self.assertEqual(
            set(schema["components"]["schemas"]["DataScopeContract"]["properties"]),
            {"case_data_scope", "call_queue", "intake_patient_lookup"},
        )
        self.assertEqual(
            schema["components"]["securitySchemes"]["jwtAuth"],
            {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        )


class FakeFirebaseSendResponse:
    def __init__(self, exception):
        self.exception = exception


class FakeFirebaseBatchResponse:
    def __init__(self, *, success_count, failure_count):
        self.success_count = success_count
        self.failure_count = failure_count
        self.responses = [FakeFirebaseSendResponse(None)] * (success_count + failure_count)


class FakeFirebaseError(Exception):
    pass


class FakeFirebaseMessaging:
    class AndroidConfig:
        def __init__(self, priority, notification=None):
            self.priority = priority
            self.notification = notification

    class MulticastMessage:
        def __init__(self, tokens, data, android, notification=None):
            self.tokens = tokens
            self.notification = notification
            self.data = data
            self.android = android


class MobileCaseCreateTests(APITestCase):
    def setUp(self):
        from patients.models import Patient, ensure_default_departments

        ensure_default_departments()
        self.Patient = Patient
        self.admin = get_user_model().objects.create_superuser(
            username="create-admin",
            email="create-admin@example.com",
            password="pass",
        )
        self.client.force_authenticate(self.admin)
        self.anc = DepartmentConfig.objects.get(name="ANC")
        self.surgery = DepartmentConfig.objects.get(name="Surgery")
        self.medicine = DepartmentConfig.objects.get(name="Medicine")

    def _post_create(self, payload):
        return self.client.post(reverse("api:case_list"), payload, format="json")

    def test_create_new_anc_case_seeds_tasks_and_rch_reminder(self):
        payload = {
            "patient_mode": "new",
            "use_temporary_uhid": True,
            "prefix": "MRS",
            "first_name": "Keerthana",
            "last_name": "Manikandan",
            "gender": "FEMALE",
            "age": 27,
            "phone_number": "9876500000",
            "category": self.anc.id,
            "diagnosis": "Antenatal follow-up",
            "high_risk": False,
            "rch_bypass": True,
            "lmp": (timezone.localdate() - timedelta(days=60)).isoformat(),
            "edd": (timezone.localdate() + timedelta(days=220)).isoformat(),
            "gravida": 1,
            "para": 0,
            "abortions": 0,
            "living": 0,
            "client_write_id": "anc-create-1",
        }

        response = self._post_create(payload)

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        case_id = body["case_id"]
        case = Case.objects.get(pk=case_id)
        self.assertEqual(case.category_id, self.anc.id)
        self.assertEqual(case.first_name, "Keerthana")
        self.assertTrue(case.patient.is_temporary_id)
        self.assertTrue(case.uhid.startswith("TMP-"))
        self.assertGreaterEqual(case.tasks.count(), 1)
        self.assertTrue(case.tasks.filter(title="Update RCH Number").exists())

    def test_create_new_surgery_case_with_subcategory_and_pathway(self):
        surgery_date = (timezone.localdate() + timedelta(days=20)).isoformat()
        payload = {
            "patient_mode": "new",
            "use_temporary_uhid": True,
            "prefix": "MR",
            "first_name": "Arun",
            "last_name": "Kumar",
            "gender": "MALE",
            "age": 45,
            "phone_number": "9876500001",
            "category": self.surgery.id,
            "subcategory": "GENERAL_SURGERY",
            "diagnosis": "Hernia",
            "surgical_pathway": "PLANNED_SURGERY",
            "surgery_date": surgery_date,
            "client_write_id": "surgery-create-1",
        }

        response = self._post_create(payload)

        self.assertEqual(response.status_code, 201, response.content)
        case = Case.objects.get(pk=response.json()["case_id"])
        self.assertEqual(case.subcategory, "GENERAL_SURGERY")
        self.assertEqual(case.surgical_pathway, "PLANNED_SURGERY")
        self.assertGreaterEqual(case.tasks.count(), 1)

    def test_create_new_medicine_case_with_review(self):
        review_date = (timezone.localdate() + timedelta(days=30)).isoformat()
        payload = {
            "patient_mode": "new",
            "use_temporary_uhid": True,
            "prefix": "MR",
            "first_name": "Suresh",
            "last_name": "Raina",
            "gender": "MALE",
            "age": 60,
            "phone_number": "9876500002",
            "category": self.medicine.id,
            "subcategory": "GENERAL_MEDICINE",
            "diagnosis": "T2DM review",
            "review_frequency": "MONTHLY",
            "review_date": review_date,
            "client_write_id": "medicine-create-1",
        }

        response = self._post_create(payload)

        self.assertEqual(response.status_code, 201, response.content)
        case = Case.objects.get(pk=response.json()["case_id"])
        self.assertEqual(case.review_frequency, "MONTHLY")
        self.assertIsNotNone(case.review_date)

    def test_create_existing_patient_case_reuses_patient(self):
        first = self._post_create(
            {
                "patient_mode": "new",
                "use_temporary_uhid": True,
                "prefix": "MR",
                "first_name": "Vikram",
                "last_name": "Singh",
                "gender": "MALE",
                "age": 50,
                "phone_number": "9876500003",
                "category": self.medicine.id,
                "subcategory": "GENERAL_MEDICINE",
                "diagnosis": "HTN",
                "review_date": (timezone.localdate() + timedelta(days=30)).isoformat(),
                "client_write_id": "existing-1",
            }
        )
        self.assertEqual(first.status_code, 201, first.content)
        patient = Case.objects.get(pk=first.json()["case_id"]).patient

        second = self._post_create(
            {
                "patient_mode": "existing",
                "selected_patient": patient.id,
                "category": self.surgery.id,
                "subcategory": "ORTHOPEDICS",
                "diagnosis": "Knee",
                "surgical_pathway": "SURVEILLANCE",
                "review_date": (timezone.localdate() + timedelta(days=15)).isoformat(),
                "client_write_id": "existing-2",
            }
        )

        self.assertEqual(second.status_code, 201, second.content)
        new_case = Case.objects.get(pk=second.json()["case_id"])
        self.assertEqual(new_case.patient_id, patient.id)
        self.assertEqual(self.Patient.objects.filter(pk=patient.id).count(), 1)

    def test_create_validation_error_returns_field_errors(self):
        response = self._post_create(
            {
                "patient_mode": "new",
                "category": self.anc.id,
                "client_write_id": "bad-1",
            }
        )

        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertIn("first_name", errors)

    def test_create_is_idempotent_on_client_write_id(self):
        payload = {
            "patient_mode": "new",
            "use_temporary_uhid": True,
            "prefix": "MRS",
            "first_name": "Divya",
            "last_name": "Nair",
            "gender": "FEMALE",
            "age": 30,
            "phone_number": "9876500004",
            "category": self.anc.id,
            "diagnosis": "ANC",
            "rch_bypass": True,
            "lmp": (timezone.localdate() - timedelta(days=60)).isoformat(),
            "edd": (timezone.localdate() + timedelta(days=220)).isoformat(),
            "gravida": 1,
            "para": 0,
            "abortions": 0,
            "living": 0,
            "client_write_id": "idem-1",
        }

        first = self._post_create(payload)
        second = self._post_create(payload)

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.json()["case_id"], second.json()["case_id"])
        self.assertEqual(Case.objects.filter(first_name="Divya").count(), 1)

    def test_create_with_real_uhid_replays_before_duplicate_validation(self):
        payload = {
            "patient_mode": "new",
            "use_temporary_uhid": False,
            "uhid": "REAL-IDEM-1",
            "prefix": "MRS",
            "first_name": "Revathi",
            "last_name": "Menon",
            "gender": "FEMALE",
            "age": 29,
            "phone_number": "9876500006",
            "category": self.anc.id,
            "diagnosis": "ANC",
            "rch_bypass": True,
            "lmp": (timezone.localdate() - timedelta(days=60)).isoformat(),
            "edd": (timezone.localdate() + timedelta(days=220)).isoformat(),
            "gravida": 1,
            "para": 0,
            "abortions": 0,
            "living": 0,
            "client_write_id": "real-uhid-idem-1",
        }

        first = self._post_create(payload)
        second = self._post_create(payload)

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.json()["case_id"], second.json()["case_id"])
        self.assertEqual(Case.objects.filter(uhid="REAL-IDEM-1").count(), 1)
        self.assertEqual(MobileWriteReceipt.objects.filter(client_write_id=_idempotency_key_digest("real-uhid-idem-1")).count(), 1)

    def test_create_denied_without_case_create_capability(self):
        group = Group.objects.create(name="ReadOnlyRole")
        RoleSetting.objects.create(role_name="ReadOnlyRole", can_note_add=True, can_case_create=False)
        viewer = get_user_model().objects.create_user(username="viewer", password="pass")
        viewer.groups.add(group)
        client = APIClient()
        client.force_authenticate(viewer)

        response = client.post(
            reverse("api:case_list"),
            {
                "patient_mode": "new",
                "use_temporary_uhid": True,
                "prefix": "MR",
                "first_name": "No",
                "last_name": "Access",
                "gender": "MALE",
                "age": 40,
                "phone_number": "9876500005",
                "category": self.medicine.id,
                "subcategory": "GENERAL_MEDICINE",
                "diagnosis": "x",
                "review_date": (timezone.localdate() + timedelta(days=30)).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_patient_search_finds_created_patient(self):
        self._post_create(
            {
                "patient_mode": "new",
                "use_temporary_uhid": True,
                "prefix": "MRS",
                "first_name": "Lakshmi",
                "last_name": "Devi",
                "gender": "FEMALE",
                "age": 33,
                "phone_number": "9876512345",
                "category": self.anc.id,
                "diagnosis": "ANC",
                "rch_bypass": True,
                "lmp": (timezone.localdate() - timedelta(days=60)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=220)).isoformat(),
                "gravida": 1,
                "para": 0,
                "abortions": 0,
                "living": 0,
                "client_write_id": "search-seed",
            }
        )

        response = self.client.post(
            reverse("api:patient_search"),
            {"query": "Lakshmi"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertTrue(any(row["name"].endswith("Lakshmi Devi") for row in results))
        self.assertEqual(set(results[0]), {"id", "uhid", "name"})

    def test_case_form_metadata_returns_choice_lists(self):
        response = self.client.get(reverse("api:case_form_metadata"))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["can_create"])
        for key in [
            "categories",
            "prefixes",
            "blood_groups",
            "genders",
            "ncd_flags",
            "anc_high_risk_reasons",
            "surgical_pathways",
            "review_frequencies",
        ]:
            self.assertIn(key, body)
            self.assertTrue(body[key])
        self.assertIn("value", body["prefixes"][0])
        self.assertIn("label", body["prefixes"][0])


class MobileEditApiTests(APITestCase):
    def setUp(self):
        from patients.models import ensure_default_departments

        ensure_default_departments()
        self.admin = get_user_model().objects.create_superuser(
            username="edit-admin",
            email="edit-admin@example.com",
            password="pass",
        )
        self.client.force_authenticate(self.admin)
        self.anc = DepartmentConfig.objects.get(name="ANC")
        self.medicine = DepartmentConfig.objects.get(name="Medicine")
        self.surgery = DepartmentConfig.objects.get(name="Surgery")
        self.case = Case.objects.create(
            uhid="UH-EDIT-1",
            prefix="MRS",
            first_name="Asha",
            last_name="Verma",
            patient_name="Asha Verma",
            gender="FEMALE",
            age=30,
            phone_number="9811100000",
            category=self.medicine,
            subcategory="GENERAL_MEDICINE",
            diagnosis="Hypertension review",
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.admin,
        )
        self.task = Task.objects.create(
            case=self.case,
            title="Initial review",
            due_date=timezone.localdate(),
            assigned_user=self.admin,
            created_by=self.admin,
        )
        self.vital = VitalEntry.objects.create(
            case=self.case,
            recorded_at=timezone.now(),
            bp_systolic=120,
            bp_diastolic=80,
            created_by=self.admin,
            updated_by=self.admin,
        )

    def _limited_client(self, **role_flags):
        user = get_user_model().objects.create_user(username=f"limited-{len(role_flags)}-{timezone.now().timestamp()}", password="pass")
        role = RoleSetting.objects.create(role_name=f"Limited {timezone.now().timestamp()}", **role_flags)
        group = Group.objects.create(name=role.role_name)
        user.groups.add(group)
        client = APIClient()
        client.force_authenticate(user)
        return client

    def _case_patch_payload(self, case, changes):
        case.refresh_from_db()
        current = _case_edit_payload(case)
        return {
            **changes,
            "base_updated_at": current["base_updated_at"],
            "base_values": {key: current[key] for key in changes},
        }

    def _task_patch_payload(self, task, changes):
        task.refresh_from_db()
        current = _task_edit_values(task)
        return {
            **changes,
            "base_updated_at": current["base_updated_at"],
            "base_values": {key: current[key] for key in changes},
        }

    def _vital_patch_payload(self, vital, changes):
        vital.refresh_from_db()
        current = _vital_edit_values(vital)
        return {
            **changes,
            "base_updated_at": current["base_updated_at"],
            "base_values": {key: current[key] for key in changes},
        }

    # --- Case edit ---
    def test_case_edit_form_returns_prefill_and_metadata(self):
        response = self.client.get(reverse("api:case_edit_form", args=[self.case.id]))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["can_edit"])
        self.assertEqual(body["case"]["diagnosis"], "Hypertension review")
        self.assertEqual(body["case"]["category"], self.medicine.id)
        self.assertTrue(len(body["categories"]) >= 1)

    def test_case_patch_updates_fields(self):
        payload = {
            "patient_mode": "existing",
            "uhid": self.case.uhid,
            "prefix": "MRS",
            "first_name": "Asha",
            "last_name": "Verma",
            "gender": "FEMALE",
            "age": 31,
            "phone_number": "9811100000",
            "category": self.medicine.id,
            "subcategory": "GENERAL_MEDICINE",
            "status": "ACTIVE",
            "diagnosis": "Hypertension stable",
            "review_date": (timezone.localdate() + timedelta(days=30)).isoformat(),
        }
        response = self.client.patch(
            reverse("api:case_detail", args=[self.case.id]), self._case_patch_payload(self.case, payload), format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.case.refresh_from_db()
        self.assertEqual(self.case.diagnosis, "Hypertension stable")
        self.assertEqual(self.case.age, 31)

    def test_case_patch_forbidden_without_capability(self):
        client = self._limited_client(can_note_add=True)
        response = client.patch(
            reverse("api:case_detail", args=[self.case.id]), {"diagnosis": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_case_patch_preserves_omitted_patient_fields(self):
        from datetime import date

        from patients.models import Patient

        dob = date(1994, 5, 1)
        patient = Patient.objects.create(
            uhid="UH-DOB-1",
            prefix="MRS",
            first_name="Asha",
            last_name="Verma",
            gender="FEMALE",
            date_of_birth=dob,
            phone_number="9811100000",
            alternate_phone_number="9000000001",
            created_by=self.admin,
        )
        case = Case.objects.create(
            uhid="UH-DOB-1",
            patient=patient,
            prefix="MRS",
            first_name="Asha",
            last_name="Verma",
            patient_name="Asha Verma",
            gender="FEMALE",
            date_of_birth=dob,
            phone_number="9811100000",
            alternate_phone_number="9000000001",
            category=self.medicine,
            subcategory="GENERAL_MEDICINE",
            diagnosis="Review",
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.admin,
        )
        # Mobile-style payload: the wizard never sends date_of_birth / alternate_phone_number.
        payload = {
            "patient_mode": "existing",
            "uhid": case.uhid,
            "prefix": "MRS",
            "first_name": "Asha",
            "last_name": "Verma",
            "gender": "FEMALE",
            "age": 31,
            "phone_number": "9811100000",
            "category": self.medicine.id,
            "subcategory": "GENERAL_MEDICINE",
            "status": "ACTIVE",
            "diagnosis": "Review updated",
            "review_date": (timezone.localdate() + timedelta(days=20)).isoformat(),
        }
        response = self.client.patch(
            reverse("api:case_detail", args=[case.id]), self._case_patch_payload(case, payload), format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        patient.refresh_from_db()
        # Fields the mobile edit omitted must survive, not be wiped.
        self.assertEqual(patient.date_of_birth, dob)
        self.assertEqual(patient.alternate_phone_number, "9000000001")

        # An explicit blank is an intentional clear and must NOT be backfilled.
        clear_payload = dict(payload)
        clear_payload["alternate_phone_number"] = ""
        clear_payload["date_of_birth"] = ""
        response = self.client.patch(
            reverse("api:case_detail", args=[case.id]), self._case_patch_payload(case, clear_payload), format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        patient.refresh_from_db()
        self.assertEqual(patient.alternate_phone_number, "")
        self.assertIsNone(patient.date_of_birth)

    def test_case_patch_preserves_omitted_surgery_fields_and_returns_complete_edit_contract(self):
        surgery_case = Case.objects.create(
            uhid="UH-SURGERY-PATCH",
            prefix="MR",
            first_name="Safe",
            last_name="Surgery",
            patient_name="Safe Surgery",
            gender="MALE",
            age=52,
            phone_number="9811100002",
            category=self.surgery,
            subcategory="GENERAL_SURGERY",
            diagnosis="Post-operative review",
            surgical_pathway="PLANNED_SURGERY",
            surgery_done=True,
            surgery_date=timezone.localdate() - timedelta(days=2),
            notes="Preserve this note",
            created_by=self.admin,
        )

        prefill = self.client.get(reverse("api:case_edit_form", args=[surgery_case.pk]))
        response = self.client.patch(
            reverse("api:case_detail", args=[surgery_case.pk]),
            self._case_patch_payload(surgery_case, {"diagnosis": "Post-operative review updated"}),
            format="json",
        )

        self.assertEqual(prefill.status_code, 200)
        self.assertTrue(prefill.json()["case"]["surgery_done"])
        self.assertEqual(response.status_code, 200, response.content)
        surgery_case.refresh_from_db()
        self.assertTrue(surgery_case.surgery_done)
        self.assertEqual(surgery_case.notes, "Preserve this note")
        self.assertTrue(response.json()["editable_case"]["surgery_done"])
        self.assertEqual(response.json()["editable_case"]["notes"], "Preserve this note")
        self.assertEqual(
            set(response.json()["editable_case"]),
            set(prefill.json()["case"]),
        )

    def test_case_patch_distinct_field_interleaving_and_same_field_conflict(self):
        base = _case_edit_payload(self.case)
        first = {
            "diagnosis": "First concurrent diagnosis",
            "base_updated_at": base["base_updated_at"],
            "base_values": {"diagnosis": base["diagnosis"]},
        }
        distinct = {
            "notes": "Independent concurrent note",
            "base_updated_at": base["base_updated_at"],
            "base_values": {"notes": base["notes"]},
        }
        stale_same = {
            "diagnosis": "Stale overwrite",
            "base_updated_at": base["base_updated_at"],
            "base_values": {"diagnosis": base["diagnosis"]},
        }
        url = reverse("api:case_detail", args=[self.case.pk])

        first_response = self.client.patch(url, first, format="json")
        distinct_response = self.client.patch(url, distinct, format="json")
        conflict_response = self.client.patch(url, stale_same, format="json")

        self.assertEqual(first_response.status_code, 200, first_response.content)
        self.assertEqual(distinct_response.status_code, 200, distinct_response.content)
        self.assertEqual(conflict_response.status_code, 409, conflict_response.content)
        self.case.refresh_from_db()
        self.assertEqual(self.case.diagnosis, "First concurrent diagnosis")
        self.assertEqual(self.case.notes, "Independent concurrent note")

    def test_case_patch_is_idempotent_and_receipt_key_is_digested(self):
        payload = self._case_patch_payload(self.case, {"diagnosis": "Idempotent patch"})
        payload["client_write_id"] = "case-patch-idempotency"
        url = reverse("api:case_detail", args=[self.case.pk])

        first = self.client.patch(url, payload, format="json")
        replay = self.client.patch(url, payload, format="json")

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(replay.status_code, 200, replay.content)
        receipt = MobileWriteReceipt.objects.get(operation="case_update")
        self.assertNotEqual(receipt.client_write_id, payload["client_write_id"])
        self.assertEqual(receipt.client_write_id, _idempotency_key_digest(payload["client_write_id"]))

    # --- Task metadata + create ---
    def test_task_form_metadata(self):
        response = self.client.get(reverse("api:task_form_metadata"))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["default_status"], "SCHEDULED")
        self.assertTrue(any(c["value"] == "VISIT" for c in body["task_types"]))
        self.assertTrue(any(u["id"] == self.admin.id for u in body["assignable_users"]))

    def test_task_create_happy_path(self):
        payload = {
            "title": "Follow-up call",
            "due_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "status": "SCHEDULED",
            "task_type": "CALL",
            "assigned_user": self.admin.id,
        }
        response = self.client.post(
            reverse("api:task_create", args=[self.case.id]), payload, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(self.case.tasks.filter(title="Follow-up call").exists())

    def test_task_create_forbidden_without_capability(self):
        client = self._limited_client(can_task_edit=True)  # case access, but no task_create
        payload = {"title": "x", "due_date": timezone.localdate().isoformat(), "status": "SCHEDULED", "task_type": "CALL"}
        response = client.post(reverse("api:task_create", args=[self.case.id]), payload, format="json")
        self.assertEqual(response.status_code, 403)

    def test_task_create_is_idempotent(self):
        payload = {
            "title": "Idempotent task",
            "due_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "status": "SCHEDULED",
            "task_type": "CALL",
            "client_write_id": "task-create-xyz",
        }
        first = self.client.post(reverse("api:task_create", args=[self.case.id]), payload, format="json")
        second = self.client.post(reverse("api:task_create", args=[self.case.id]), payload, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        # Same client_write_id replays the first result instead of creating a duplicate.
        self.assertEqual(self.case.tasks.filter(title="Idempotent task").count(), 1)

    # --- Task edit / reschedule / reopen / note ---
    def test_task_patch_can_unassign(self):
        self.assertIsNotNone(self.task.assigned_user_id)
        response = self.client.patch(
            reverse("api:task_detail", args=[self.task.id]), self._task_patch_payload(self.task, {"assigned_user": ""}), format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.assigned_user_id)

    # --- Task edit / reschedule / reopen / note ---
    def test_task_patch_reschedule(self):
        new_date = (timezone.localdate() + timedelta(days=5)).isoformat()
        response = self.client.patch(
            reverse("api:task_detail", args=[self.task.id]), self._task_patch_payload(self.task, {"due_date": new_date}), format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.due_date.isoformat(), new_date)

    def test_task_patch_reopen_completed(self):
        self.task.status = TaskStatus.COMPLETED
        self.task.save()
        response = self.client.patch(
            reverse("api:task_detail", args=[self.task.id]), self._task_patch_payload(self.task, {"status": "SCHEDULED"}), format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SCHEDULED)

    def test_task_patch_distinct_field_interleaving_and_same_field_conflict(self):
        base = _task_edit_values(self.task)
        first_date = (timezone.localdate() + timedelta(days=4)).isoformat()
        url = reverse("api:task_detail", args=[self.task.pk])
        first = self.client.patch(
            url,
            {"due_date": first_date, "base_updated_at": base["base_updated_at"], "base_values": {"due_date": base["due_date"]}},
            format="json",
        )
        distinct = self.client.patch(
            url,
            {"notes": "Concurrent task note", "base_updated_at": base["base_updated_at"], "base_values": {"notes": base["notes"]}},
            format="json",
        )
        stale = self.client.patch(
            url,
            {"due_date": (timezone.localdate() + timedelta(days=6)).isoformat(), "base_updated_at": base["base_updated_at"], "base_values": {"due_date": base["due_date"]}},
            format="json",
        )
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(distinct.status_code, 200, distinct.content)
        self.assertEqual(stale.status_code, 409, stale.content)

    def test_task_note_creates_timeline_entry(self):
        response = self.client.post(
            reverse("api:task_note", args=[self.task.id]), {"note": "Patient confirmed visit"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.notes, "Patient confirmed visit")
        self.assertTrue(
            self.case.activity_logs.filter(note__icontains="Patient confirmed visit").exists()
        )

    # --- Vitals edit ---
    def test_vitals_patch_updates_values(self):
        payload = {"bp_systolic": 130, "bp_diastolic": 85, "pr": 78}
        response = self.client.patch(
            reverse("api:vitals_detail", args=[self.vital.id]), self._vital_patch_payload(self.vital, payload), format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.vital.refresh_from_db()
        self.assertEqual(self.vital.bp_systolic, 130)
        self.assertEqual(self.vital.pr, 78)

    def test_vitals_patch_requires_metric(self):
        response = self.client.patch(
            reverse("api:vitals_detail", args=[self.vital.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_vitals_patch_preserves_unsent_metrics(self):
        vital = VitalEntry.objects.create(
            case=self.case,
            recorded_at=timezone.now(),
            bp_systolic=118,
            bp_diastolic=76,
            pr=80,
            spo2=98,
            created_by=self.admin,
            updated_by=self.admin,
        )
        response = self.client.patch(
            reverse("api:vitals_detail", args=[vital.id]),
            self._vital_patch_payload(vital, {"bp_systolic": 132, "bp_diastolic": 88}),
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        vital.refresh_from_db()
        self.assertEqual(vital.bp_systolic, 132)
        # Metrics not included in the PATCH must be left untouched, not wiped to null.
        self.assertEqual(vital.pr, 80)
        self.assertEqual(vital.spo2, 98)

    def test_vitals_patch_distinct_field_interleaving_and_same_field_conflict(self):
        base = _vital_edit_values(self.vital)
        url = reverse("api:vitals_detail", args=[self.vital.pk])
        first = self.client.patch(
            url,
            {"pr": 81, "base_updated_at": base["base_updated_at"], "base_values": {"pr": base["pr"]}},
            format="json",
        )
        distinct = self.client.patch(
            url,
            {"spo2": 97, "base_updated_at": base["base_updated_at"], "base_values": {"spo2": base["spo2"]}},
            format="json",
        )
        stale = self.client.patch(
            url,
            {"pr": 82, "base_updated_at": base["base_updated_at"], "base_values": {"pr": base["pr"]}},
            format="json",
        )
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(distinct.status_code, 200, distinct.content)
        self.assertEqual(stale.status_code, 409, stale.content)
