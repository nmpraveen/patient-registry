import hashlib
from datetime import timedelta
from io import StringIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from patients.models import CallLog, Case, DepartmentConfig, RoleSetting, Task, TaskStatus, VitalEntry

from .admin import MobileDeviceTokenAdmin
from .models import MobileDeviceToken, MobileNotification, MobileNotificationType, MobileWriteReceipt
from .push import (
    _build_multicast_message,
    _channel_id_for_notification,
    _deactivate_permanently_failed_tokens,
    firebase_configured,
    send_mobile_notification,
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

    def test_case_api_allows_real_jwt_user_with_case_data_role(self):
        mobile_user = get_user_model().objects.create_user(username="mobile-role", password="pass")
        RoleSetting.objects.create(role_name="Mobile Staff", can_task_edit=True)
        group = Group.objects.create(name="Mobile Staff")
        mobile_user.groups.add(group)
        client = APIClient()
        token_response = client.post(
            reverse("api:token_obtain_pair"),
            {"username": "mobile-role", "password": "pass"},
            format="json",
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.json()['access']}")

        response = client.get(reverse("api:case_list"), {"bucket": "today", "assigned_to": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["uhid"], "UH-API-1")

    def test_case_list_defaults_to_all_scope_for_doctor(self):
        doctor = get_user_model().objects.create_user(username="doctor-mobile", password="pass")
        RoleSetting.objects.update_or_create(role_name="Doctor", defaults={"can_task_edit": True})
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
        RoleSetting.objects.update_or_create(role_name="Mobile Staff", defaults={"can_task_edit": True})
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

    def test_logout_returns_json_contract_for_android_client(self):
        refresh = RefreshToken.for_user(self.user)

        response = self.client.post(
            reverse("api:logout"),
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Logged out.")

    def test_logout_deactivates_mobile_device_tokens(self):
        refresh = RefreshToken.for_user(self.user)
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
        refresh = RefreshToken.for_user(self.user)
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
        search = self.client.get(
            reverse("api:case_list"),
            {"bucket": "today", "assigned_to": "me", "q": "Diabetes"},
        )

        self.assertEqual(page_one.status_code, 200)
        self.assertIsNotNone(page_one.json()["next"])
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["count"], 1)
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
        self.assertEqual(MobileWriteReceipt.objects.filter(client_write_id="complete-1").count(), 1)

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
        self.assertFalse(MobileWriteReceipt.objects.filter(client_write_id="hidden-task-complete").exists())

    def test_failed_idempotent_write_replay_preserves_error_status(self):
        url = reverse("api:task_complete", kwargs={"pk": self.awaiting_task.pk})

        first = self.client.post(url, {"client_write_id": "future-anc-complete"}, format="json")
        second = self.client.post(url, {"client_write_id": "future-anc-complete"}, format="json")

        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(first.json(), second.json())
        receipt = MobileWriteReceipt.objects.get(client_write_id="future-anc-complete")
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
        self.assertEqual(call_log.created_at, attempted_at)
        self.assertEqual(parse_datetime(response.json()["call_log"]["created_at"]), attempted_at)

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
        self.assertEqual(MobileWriteReceipt.objects.filter(client_write_id="call-repeat-1").count(), 1)

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
        self.assertEqual(MobileWriteReceipt.objects.filter(client_write_id="vital-repeat-1").count(), 1)

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
            title="Red flag patient",
            case=self.case,
            payload={"case_id": self.case.id},
        )

        self.assertFalse(firebase_configured())
        result = send_mobile_notification(notification)

        self.assertEqual(result["sent"], False)
        self.assertEqual(result["reason"], "fcm_not_configured")

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

    def test_push_message_sets_android_channel_and_priority(self):
        notification = MobileNotification.objects.create(
            user=self.user,
            notification_type=MobileNotificationType.RED_FLAG,
            title="Red flag patient",
            body="Priya Sharma: High risk",
            case=self.case,
            payload={"type": MobileNotificationType.RED_FLAG, "channel": "red_flags", "case_id": self.case.id},
        )

        message = _build_multicast_message(FakeFirebaseMessaging, notification, ["token-1"])

        self.assertEqual(message.tokens, ["token-1"])
        self.assertEqual(message.android.priority, "high")
        self.assertEqual(message.android.notification.channel_id, "red_flags")
        self.assertEqual(message.data["case_id"], str(self.case.id))
        self.assertEqual(message.data["title"], "Red flag patient")

    def test_push_channel_mapping_defaults_to_overdue(self):
        notification = MobileNotification(
            user=self.user,
            notification_type="unexpected",
            title="Unknown",
            payload={"channel": "unknown"},
        )

        self.assertEqual(_channel_id_for_notification(notification), "overdue")

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
        self.assertEqual(notifications.get().payload["case_id"], self.case.id)
        self.assertEqual(notifications.get().payload["phone_number"], self.case.phone_number)

    def test_task_reassignment_notifies_new_assignee(self):
        new_user = get_user_model().objects.create_user(username="new-assignee", password="pass")
        self.task.assigned_user = new_user
        self.task.save(update_fields=["assigned_user", "updated_at"])

        notification = MobileNotification.objects.get(
            user=new_user,
            notification_type=MobileNotificationType.ASSIGNMENT,
            task=self.task,
        )
        self.assertEqual(notification.payload["type"], MobileNotificationType.ASSIGNMENT)

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
        self.assertEqual(notifications.get().payload["channel"], "red_flags")
        self.assertEqual(notifications.get().payload["phone_number"], "9876543211")

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
        self.assertEqual(notifications.get().payload["days_overdue"], 2)

    def test_notification_read_marks_only_current_users_notification(self):
        other_user = get_user_model().objects.create_user(username="other-user", password="pass")
        notification = MobileNotification.objects.create(
            user=self.user,
            notification_type=MobileNotificationType.ASSIGNMENT,
            title="Open case",
            case=self.case,
            payload={"case_id": self.case.id},
        )
        other_notification = MobileNotification.objects.create(
            user=other_user,
            notification_type=MobileNotificationType.ASSIGNMENT,
            title="Other case",
            case=self.case,
            payload={"case_id": self.case.id},
        )

        response = self.client.post(reverse("api:notification_read", kwargs={"pk": notification.pk}))
        forbidden = self.client.post(reverse("api:notification_read", kwargs={"pk": other_notification.pk}))

        self.assertEqual(response.status_code, 200)
        notification.refresh_from_db()
        other_notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.assertIsNone(other_notification.read_at)
        self.assertEqual(forbidden.status_code, 404)


class FakeFirebaseSendResponse:
    def __init__(self, exception):
        self.exception = exception


class FakeFirebaseError(Exception):
    pass


class FakeFirebaseMessaging:
    class Notification:
        def __init__(self, title, body):
            self.title = title
            self.body = body

    class AndroidNotification:
        def __init__(self, channel_id):
            self.channel_id = channel_id

    class AndroidConfig:
        def __init__(self, priority, notification):
            self.priority = priority
            self.notification = notification

    class MulticastMessage:
        def __init__(self, tokens, notification, data, android):
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

        response = self.client.get(reverse("api:patient_search"), {"q": "Lakshmi"})

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertTrue(any(row["first_name"] == "Lakshmi" for row in results))

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
