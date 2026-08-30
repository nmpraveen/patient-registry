from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import importlib
import io
import time
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import MobileDeviceToken

from .audit import record_audit_event
from .auth_security import (
    AUTH_VERSION_SESSION_KEY,
    _client_ip,
    bump_auth_version,
    cleanup_expired_auth_buckets,
    consume_auth_attempt,
    current_auth_version,
)
from .forms import CaseForm, PatientForm, UserManagementCreateForm, UserManagementUpdateForm
from .models import (
    AuditEvent,
    AuthenticationThrottleBucket,
    Case,
    CaseDataScope,
    DepartmentConfig,
    DeviceApprovalPolicy,
    Patient,
    PatientMergeRecovery,
    RoleSetting,
    StaffDeviceCredential,
    StaffDeviceCredentialStatus,
    StaffMobileDeviceCredential,
    Task,
    TaskStatus,
    TaskType,
    VitalEntry,
    generate_temporary_patient_uhid,
)
from .merge_recovery import recover_patient_merge
from .policy import can_access_case_data, effective_role_policy
from .views import _accessible_case_queryset, _merge_patient_records, _patient_search_queryset
from .test_client import AuthVersionTestClient


TestCase.client_class = AuthVersionTestClient
TransactionTestCase.client_class = AuthVersionTestClient


User = get_user_model()


class SecurityFixtureMixin:
    def setUp(self):
        super().setUp()
        self.category = DepartmentConfig.objects.order_by("pk").first()
        if self.category is None:
            self.category = DepartmentConfig.objects.create(name="Security Test")
        self.owner = User.objects.create_user(username="security-owner", password="owner-password-123")
        self.other = User.objects.create_user(username="security-other", password="other-password-123")

    def create_case(self, *, uhid, created_by=None, patient=None):
        created_by = created_by or self.owner
        if patient is None:
            patient = Patient.objects.create(
                uhid=uhid,
                first_name="Security",
                last_name="Patient",
                phone_number="9000000001",
                created_by=created_by,
            )
        return Case.objects.create(
            patient=patient,
            uhid=patient.uhid,
            first_name=patient.first_name,
            last_name=patient.last_name,
            phone_number=patient.phone_number,
            category=self.category,
            created_by=created_by,
        )

    def assign_case(self, case, user):
        return Task.objects.create(
            case=case,
            title="Assigned security task",
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            task_type=TaskType.CALL,
            assigned_user=user,
            created_by=self.owner,
        )

    def add_role(self, user, *, name, **settings_values):
        RoleSetting.objects.create(role_name=name, **settings_values)
        group = Group.objects.create(name=name)
        user.groups.add(group)


class ExplicitRoleScopeTests(SecurityFixtureMixin, TestCase):
    def test_custom_all_scope_is_not_tied_to_doctor_or_admin_names(self):
        self.add_role(self.other, name="Clinical Lead", case_data_scope=CaseDataScope.ALL)
        first = self.create_case(uhid="SCOPE-001")
        second = self.create_case(uhid="SCOPE-002")

        visible_ids = set(_accessible_case_queryset(self.other).values_list("pk", flat=True))

        self.assertEqual(visible_ids, {first.pk, second.pk})

    def test_role_names_never_grant_implicit_scope_and_renamed_roles_are_equivalent(self):
        doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        renamed_group = Group.objects.create(name="Renamed Clinical Role")
        RoleSetting.objects.update_or_create(
            role_name=doctor_group.name,
            defaults={
                "case_data_scope": CaseDataScope.NONE,
                "can_access_call_queue": False,
                "can_intake_patient_lookup": False,
                "can_case_create": True,
                "can_case_edit": False,
                "can_task_create": False,
                "can_task_edit": False,
                "can_task_reopen": False,
                "can_note_add": False,
                "can_patient_merge": False,
                "can_manage_settings": False,
            },
        )
        RoleSetting.objects.create(
            role_name=renamed_group.name,
            case_data_scope=CaseDataScope.NONE,
            can_case_create=True,
        )
        doctor_named_user = User.objects.create_user(username="doctor-name-only")
        renamed_user = User.objects.create_user(username="renamed-name-only")
        doctor_named_user.groups.add(doctor_group)
        renamed_user.groups.add(renamed_group)

        doctor_policy = effective_role_policy(doctor_named_user)
        renamed_policy = effective_role_policy(renamed_user)

        self.assertEqual(doctor_policy.case_data_scope, renamed_policy.case_data_scope)
        self.assertEqual(doctor_policy.capabilities, renamed_policy.capabilities)
        self.assertFalse(can_access_case_data(doctor_named_user))
        self.assertFalse(can_access_case_data(renamed_user))

    def test_data_migration_does_not_expand_custom_role_phi_scope(self):
        custom = RoleSetting.objects.create(
            role_name="Custom Intake-Like Role",
            can_case_create=True,
            can_note_add=True,
            case_data_scope=CaseDataScope.ALL,
            can_access_call_queue=True,
            can_intake_patient_lookup=True,
        )
        migration = importlib.import_module(
            "patients.migrations.0037_backend_auth_clinical_security"
        )
        from django.apps import apps as django_apps

        migration.backfill_role_scopes(django_apps, None)

        custom.refresh_from_db()
        self.assertEqual(custom.case_data_scope, CaseDataScope.NONE)
        self.assertFalse(custom.can_access_call_queue)
        self.assertFalse(custom.can_intake_patient_lookup)

    def test_call_queue_and_intake_lookup_require_explicit_scope_flags(self):
        self.add_role(
            self.other,
            name="Scoped Caller",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_note_add=True,
            can_case_create=True,
        )
        queue_case = self.create_case(uhid="SCOPE-QUEUE")
        Task.objects.create(
            case=queue_case,
            title="Call today",
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            task_type=TaskType.CALL,
            created_by=self.owner,
        )
        directory_patient = Patient.objects.create(
            uhid="SCOPE-DIRECTORY",
            first_name="Directory",
            last_name="Only",
            phone_number="9000000002",
            created_by=self.owner,
        )

        self.assertFalse(_accessible_case_queryset(self.other).filter(pk=queue_case.pk).exists())
        self.assertFalse(
            _patient_search_queryset("Directory", user=self.other, allow_intake_lookup=True)
            .filter(pk=directory_patient.pk)
            .exists()
        )

        role = RoleSetting.objects.get(role_name="Scoped Caller")
        role.can_access_call_queue = True
        role.can_intake_patient_lookup = True
        role.save(update_fields=["can_access_call_queue", "can_intake_patient_lookup"])
        refreshed_user = User.objects.get(pk=self.other.pk)

        self.assertTrue(_accessible_case_queryset(refreshed_user).filter(pk=queue_case.pk).exists())
        self.assertFalse(
            _patient_search_queryset("Directory", user=refreshed_user, allow_intake_lookup=True)
            .filter(pk=directory_patient.pk)
            .exists()
        )
        directory_case = self.create_case(uhid="SCOPE-DIRECTORY-CASE", patient=directory_patient)
        self.assign_case(directory_case, self.other)
        self.assertTrue(
            _patient_search_queryset("Directory", user=refreshed_user, allow_intake_lookup=True)
            .filter(pk=directory_patient.pk)
            .exists()
        )


class AffectedSetAuthorizationTests(SecurityFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.add_role(
            self.other,
            name="Limited Editor",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_case_edit=True,
            can_patient_merge=True,
        )
        self.client.force_login(self.other)

    def test_patient_edit_is_denied_when_any_mirrored_case_is_inaccessible(self):
        patient = Patient.objects.create(
            uhid="EDIT-AFFECTED",
            first_name="Affected",
            last_name="Edit",
            phone_number="9000000003",
            created_by=self.owner,
        )
        accessible = self.create_case(uhid="EDIT-AFFECTED-A", patient=patient)
        self.assign_case(accessible, self.other)
        self.create_case(uhid="EDIT-AFFECTED-B", patient=patient)

        response = self.client.get(reverse("patients:patient_edit", kwargs={"pk": patient.pk}))

        self.assertEqual(response.status_code, 403)

    def test_merge_is_denied_when_target_contains_an_inaccessible_case(self):
        source = Patient.objects.create(
            uhid="MERGE-SOURCE",
            first_name="Merge",
            last_name="Source",
            phone_number="9000000004",
            created_by=self.other,
        )
        source_case = self.create_case(uhid="MERGE-SOURCE-A", patient=source, created_by=self.other)
        self.assign_case(source_case, self.other)
        target = Patient.objects.create(
            uhid="MERGE-TARGET",
            first_name="Merge",
            last_name="Target",
            phone_number="9000000005",
            created_by=self.owner,
        )
        accessible_target = self.create_case(uhid="MERGE-TARGET-A", patient=target)
        self.assign_case(accessible_target, self.other)
        blocked_target = self.create_case(uhid="MERGE-TARGET-B", patient=target)

        response = self.client.post(
            reverse("patients:patient_merge", kwargs={"pk": source.pk}),
            {
                "target_patient": target.pk,
                "confirm_target_uhid": target.uhid,
                "confirm_merge": "on",
            },
        )

        self.assertEqual(response.status_code, 403)
        source.refresh_from_db()
        blocked_target.refresh_from_db()
        self.assertIsNone(source.merged_into_id)
        self.assertEqual(blocked_target.patient_id, target.pk)


class PasswordAndSessionSecurityTests(TestCase):
    def test_user_management_forms_apply_django_password_validation(self):
        role = Group.objects.create(name="Validated User")
        RoleSetting.objects.create(role_name=role.name, case_data_scope=CaseDataScope.NONE)
        create_form = UserManagementCreateForm(
            data={
                "first_name": "Weak",
                "last_name": "Password",
                "username": "weak-password-user",
                "is_active": "on",
                "role": role.pk,
                "password1": "password",
                "password2": "password",
            }
        )
        self.assertFalse(create_form.is_valid())
        self.assertIn("password1", create_form.errors)

        user = User.objects.create_user(username="update-password-user", password="old-strong-password-123")
        user.groups.add(role)
        update_form = UserManagementUpdateForm(
            data={
                "first_name": "Weak",
                "last_name": "Password",
                "username": user.username,
                "is_active": "on",
                "role": role.pk,
                "password1": "12345678",
                "password2": "12345678",
            },
            instance=user,
        )
        self.assertFalse(update_form.is_valid())
        self.assertIn("password1", update_form.errors)

    @override_settings(AUTH_THROTTLE_ACCOUNT_LIMIT=2, AUTH_THROTTLE_IP_LIMIT=20)
    def test_web_login_is_throttled_by_account_and_ip(self):
        User.objects.create_user(username="throttled-web", password="strong-password-123")
        url = reverse("login")

        self.assertEqual(self.client.post(url, {"username": "throttled-web", "password": "wrong"}).status_code, 200)
        self.assertEqual(self.client.post(url, {"username": "throttled-web", "password": "wrong"}).status_code, 200)
        blocked = self.client.post(url, {"username": "throttled-web", "password": "strong-password-123"})

        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked)

    def test_password_change_invalidates_an_existing_web_session(self):
        user = User.objects.create_user(username="session-user", password="strong-password-123")
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "strong-password-123"},
        )
        self.assertEqual(response.status_code, 302)

        user.set_password("new-strong-password-456")
        user.save(update_fields=["password"])
        revoked = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(revoked.status_code, 302)
        self.assertTrue(revoked.url.startswith(reverse("login")))

    def test_admin_login_uses_device_aware_flow_and_revocation_ends_admin_session(self):
        user = User.objects.create_superuser(
            username="device-admin",
            password="strong-password-123",
            email="admin@example.invalid",
        )
        policy = DeviceApprovalPolicy.get_solo()
        policy.enabled = True
        policy.save()
        policy.target_users.add(user)
        raw_token = "approved-browser-token"
        credential = StaffDeviceCredential.objects.create(
            user=user,
            status=StaffDeviceCredentialStatus.APPROVED,
            device_label="Admin browser",
            credential_id="admin-credential",
            public_key="public-key",
            trusted_token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            trusted_token_created_at=timezone.now(),
            approved_at=timezone.now(),
        )
        client = Client()
        client.cookies[settings.DEVICE_APPROVAL_TRUST_COOKIE_NAME] = f"{credential.pk}:{raw_token}"

        redirect_to_login = client.get("/admin/login/")
        self.assertEqual(redirect_to_login.status_code, 302)
        self.assertIn(reverse("login"), redirect_to_login.url)
        login = client.post(
            reverse("login"),
            {"username": user.username, "password": "strong-password-123", "next": "/admin/"},
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.url, "/admin/")
        self.assertEqual(client.get("/admin/").status_code, 200)

        credential.status = StaffDeviceCredentialStatus.REVOKED
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["status", "revoked_at"])
        revoked = client.get("/admin/")

        self.assertEqual(revoked.status_code, 302)
        self.assertTrue(revoked.url.startswith(reverse("login")))

    def test_group_target_requires_approved_browser_and_group_change_revokes_session(self):
        user = User.objects.create_user(
            username="group-browser-user",
            password="strong-password-123",
        )
        group = Group.objects.create(name="Browser Approval Group")
        user.groups.add(group)
        policy = DeviceApprovalPolicy.get_solo()
        policy.enabled = True
        policy.save()
        policy.target_groups.add(group)

        denied_client = Client()
        denied = denied_client.post(
            reverse("login"),
            {"username": user.username, "password": "strong-password-123"},
        )
        self.assertEqual(denied.status_code, 302)
        self.assertEqual(denied.url, reverse("login_device_verification"))
        self.assertNotIn("_auth_user_id", denied_client.session)

        raw_token = "group-approved-browser-token"
        credential = StaffDeviceCredential.objects.create(
            user=user,
            status=StaffDeviceCredentialStatus.APPROVED,
            device_label="Approved group browser",
            credential_id="group-browser-credential",
            public_key="public-key",
            trusted_token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            trusted_token_created_at=timezone.now(),
            approved_at=timezone.now(),
        )
        approved_client = Client()
        approved_client.cookies[settings.DEVICE_APPROVAL_TRUST_COOKIE_NAME] = (
            f"{credential.pk}:{raw_token}"
        )
        approved = approved_client.post(
            reverse("login"),
            {"username": user.username, "password": "strong-password-123"},
        )
        self.assertEqual(approved.status_code, 302)
        self.assertIn("_auth_user_id", approved_client.session)

        user.groups.remove(group)
        revoked = approved_client.get(reverse("patients:dashboard"))
        self.assertEqual(revoked.status_code, 302)
        self.assertTrue(revoked.url.startswith(reverse("login")))


class VitalAndAuditConstraintTests(SecurityFixtureMixin, TestCase):
    def test_vital_model_and_database_reject_out_of_range_values(self):
        case = self.create_case(uhid="VITAL-RANGE")
        vital = VitalEntry(case=case, bp_systolic=1, bp_diastolic=1, spo2=1)

        with self.assertRaises(ValidationError):
            vital.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            VitalEntry.objects.create(case=case, spo2=1)

    def test_clinical_and_data_events_are_append_only(self):
        case = self.create_case(uhid="AUDIT-CASE")
        case.notes = "Changed without copying clinical text into the audit event."
        case.save(update_fields=["notes", "updated_at"])
        case_id = case.pk
        case.delete()

        self.assertTrue(
            AuditEvent.objects.filter(action="patients.case.created", object_id=str(case_id)).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(action="patients.case.updated", object_id=str(case_id)).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(action="patients.case.deleted", object_id=str(case_id)).exists()
        )
        event = AuditEvent.objects.filter(object_id=str(case_id)).first()
        event.action = "tampered"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            AuditEvent.objects.filter(pk=event.pk).update(action="tampered")

    def test_patient_data_export_is_audited_without_bundle_content(self):
        admin = User.objects.create_superuser(
            username="export-admin",
            password="strong-password-123",
            email="export@example.invalid",
        )
        self.client.force_login(admin)

        response = self.client.post(reverse("patients:settings_database"), {"action": "export"})

        self.assertEqual(response.status_code, 200)
        event = AuditEvent.objects.get(action="patient_data.exported", actor_user_id=admin.pk)
        self.assertEqual(set(event.metadata), {"archive_size_bytes"})

    def test_iam_delete_and_sensitive_metadata_are_audited_safely(self):
        deleted_user_id = self.other.pk
        self.other.delete()

        self.assertTrue(
            AuditEvent.objects.filter(
                action="auth.user.deleted",
                object_id=str(deleted_user_id),
            ).exists()
        )
        event = record_audit_event(
            category=AuditEvent.Category.IAM,
            action="metadata.redaction.test",
            metadata={"refresh_token": "must-not-be-stored", "safe_count": 3},
        )
        self.assertEqual(event.metadata, {"refresh_token": "[redacted]", "safe_count": 3})


class FailClosedSessionAndIntegrationTests(TestCase):
    def test_unbound_and_malformed_authenticated_sessions_are_logged_out(self):
        user = User.objects.create_user(username="legacy-session", password="strong-password-123")
        for malformed in (None, "1", 0, -1):
            client = Client()
            client.force_login(user)
            if malformed is not None:
                session = client.session
                session[AUTH_VERSION_SESSION_KEY] = malformed
                session.save()
            response = client.get(reverse("patients:dashboard"))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse("login")))
            self.assertNotIn("_auth_user_id", client.session)

    def test_auth_version_bump_atomically_deactivates_mobile_delivery_tokens(self):
        user = User.objects.create_user(username="delivery-revoke", password="strong-password-123")
        token = MobileDeviceToken.objects.create(user=user, token="delivery-token", is_active=True)
        before = current_auth_version(user)

        bump_auth_version(user, reason="test_security_change")

        token.refresh_from_db()
        self.assertFalse(token.is_active)
        self.assertGreater(current_auth_version(user), before)

    def test_auth_version_and_mobile_deactivation_roll_back_if_audit_fails(self):
        user = User.objects.create_user(username="delivery-audit-fail", password="strong-password-123")
        token = MobileDeviceToken.objects.create(user=user, token="delivery-token-fail", is_active=True)
        before = current_auth_version(user)

        with patch("patients.audit.record_audit_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                bump_auth_version(user, reason="forced_failure")

        token.refresh_from_db()
        self.assertTrue(token.is_active)
        self.assertEqual(current_auth_version(user), before)

    @override_settings(
        AUTH_TRUSTED_PROXY_CIDRS=["10.0.0.0/8"],
        AUTH_CLIENT_IP_HEADER="HTTP_X_FORWARDED_FOR",
    )
    def test_client_ip_ignores_spoofed_headers_and_uses_trusted_proxy_chain(self):
        factory = RequestFactory()
        untrusted = factory.get(
            "/login/",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_FORWARDED_FOR="198.51.100.77",
        )
        proxied = factory.get(
            "/login/",
            REMOTE_ADDR="10.0.0.5",
            HTTP_X_FORWARDED_FOR="192.0.2.99, 198.51.100.44, 10.0.0.4",
        )

        self.assertEqual(_client_ip(untrusted), "203.0.113.10")
        self.assertEqual(_client_ip(proxied), "198.51.100.44")

    @override_settings(
        AUTH_TRUSTED_PROXY_CIDRS=["10.0.0.0/8"],
        AUTH_CLIENT_IP_HEADER="HTTP_X_FORWARDED_FOR",
        AUTH_THROTTLE_IP_LIMIT=1,
        AUTH_THROTTLE_ACCOUNT_LIMIT=20,
    )
    def test_spoofed_forwarded_headers_cannot_split_the_global_ip_lockout(self):
        factory = RequestFactory()
        first = factory.post(
            "/login/",
            REMOTE_ADDR="203.0.113.50",
            HTTP_X_FORWARDED_FOR="198.51.100.1",
        )
        second = factory.post(
            "/login/",
            REMOTE_ADDR="203.0.113.50",
            HTTP_X_FORWARDED_FOR="198.51.100.2",
        )

        self.assertEqual(consume_auth_attempt(scope="web", request=first, identifier="one"), 0)
        self.assertGreater(consume_auth_attempt(scope="web", request=second, identifier="two"), 0)
        self.assertEqual(AuthenticationThrottleBucket.objects.filter(scope="web:ip").count(), 1)
        self.assertEqual(AuthenticationThrottleBucket.objects.filter(scope="web:account").count(), 1)

    @override_settings(
        AUTH_THROTTLE_WINDOW_SECONDS=1,
        AUTH_THROTTLE_BLOCK_SECONDS=1,
        AUTH_THROTTLE_RETENTION_SECONDS=2,
        AUTH_THROTTLE_CLEANUP_BATCH_SIZE=1,
    )
    def test_expired_throttle_bucket_cleanup_is_bounded(self):
        first = AuthenticationThrottleBucket.objects.create(scope="jwt:ip", key_hash="stale-1")
        second = AuthenticationThrottleBucket.objects.create(scope="jwt:ip", key_hash="stale-2")
        AuthenticationThrottleBucket.objects.filter(pk__in=[first.pk, second.pk]).update(
            updated_at=timezone.now() - timedelta(seconds=10)
        )

        self.assertEqual(cleanup_expired_auth_buckets(), 1)
        self.assertEqual(AuthenticationThrottleBucket.objects.filter(pk__in=[first.pk, second.pk]).count(), 1)

    @override_settings(ALLOW_MOCK_DATA_SEEDING=False)
    def test_mock_seed_command_and_settings_action_fail_closed(self):
        with self.assertRaises(CommandError):
            call_command("seed_mock_data", "--count", "1")

        admin = User.objects.create_superuser(
            username="seed-disabled-admin",
            password="strong-password-123",
            email="seed-disabled@example.invalid",
        )
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("patients:settings_seed_mock_data")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("patients:settings_seed_mock_data"),
                {"action": "seed", "profile": "smoke"},
            ).status_code,
            403,
        )

    @override_settings(ALLOW_MOCK_DATA_SEEDING=True)
    def test_enabled_mock_seed_uses_unusable_demo_credentials_and_logs_no_secret(self):
        output = io.StringIO()
        call_command("seed_mock_data", "--count", "1", stdout=output)

        demo_users = User.objects.filter(username__startswith="demo_")
        self.assertTrue(demo_users.exists())
        self.assertTrue(all(not user.has_usable_password() for user in demo_users))
        self.assertNotIn("password", output.getvalue().casefold())
        self.assertNotIn("pass", output.getvalue().casefold())


class CaseIntakeSelectionSecurityTests(SecurityFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.category, _ = DepartmentConfig.objects.get_or_create(name="Intake Security")

    def _payload(self, patient, *, client_write_id="intake-security"):
        return {
            "patient_mode": "existing",
            "selected_patient": patient.pk,
            "category": self.category.pk,
            "diagnosis": "Scoped intake",
            "client_write_id": client_write_id,
        }

    def test_denied_web_prefill_and_identity_matching_leak_no_patient_identity(self):
        self.add_role(
            self.other,
            name="Create Without Intake",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_case_create=True,
            can_intake_patient_lookup=False,
        )
        patient = Patient.objects.create(
            uhid="HIDDEN-INTAKE",
            first_name="Hidden",
            last_name="Identity",
            phone_number="9123456780",
            created_by=self.owner,
        )
        self.create_case(uhid="HIDDEN-INTAKE-CASE", patient=patient)
        self.client.force_login(self.other)

        response = self.client.get(
            reverse("patients:case_create"),
            {"patient_mode": "existing", "patient_id": patient.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, patient.uhid)
        self.assertNotContains(response, patient.first_name)
        self.assertNotContains(response, patient.phone_number)

        identity_check = self.client.post(
            reverse("patients:case_create_identity_check"),
            {
                "patient_mode": "new",
                "uhid": patient.uhid,
                "phone_number": patient.phone_number,
            },
        )
        web_search = self.client.get(
            reverse("patients:patient_search"),
            {"q": patient.first_name},
        )
        api_client = APIClient()
        api_client.force_authenticate(self.other)
        api_search = api_client.get(reverse("api:patient_search"), {"q": patient.first_name})

        self.assertEqual(identity_check.status_code, 200)
        self.assertNotContains(identity_check, patient.uhid)
        self.assertNotContains(identity_check, patient.phone_number)
        self.assertEqual(web_search.json()["results"], [])
        self.assertEqual(api_search.status_code, 200)
        self.assertEqual(api_search.json()["count"], 0)
        self.assertNotIn(patient.uhid, api_search.content.decode())
        self.assertNotIn(patient.phone_number, api_search.content.decode())

    def test_forged_web_and_api_patient_ids_are_denied_without_writes(self):
        self.add_role(
            self.other,
            name="Forged Intake",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_case_create=True,
            can_intake_patient_lookup=False,
        )
        patient = Patient.objects.create(
            uhid="FORGED-INTAKE",
            first_name="Forged",
            last_name="Hidden",
            phone_number="9123456781",
            created_by=self.owner,
        )
        self.client.force_login(self.other)
        before = Case.objects.count()
        web_response = self.client.post(reverse("patients:case_create"), self._payload(patient))
        api_client = APIClient()
        api_client.force_authenticate(self.other)
        api_response = api_client.post(reverse("api:case_list"), self._payload(patient), format="json")

        self.assertEqual(web_response.status_code, 200)
        self.assertEqual(api_response.status_code, 403)
        self.assertEqual(Case.objects.count(), before)
        denied_event = AuditEvent.objects.get(action="case.intake_patient_selection_denied")
        self.assertNotIn(str(patient.pk), str(denied_event.metadata))
        self.assertNotIn(patient.uhid, str(denied_event.metadata))

    def test_assigned_and_all_scopes_resolve_only_permitted_patients(self):
        self.add_role(
            self.other,
            name="Assigned Intake",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_case_create=True,
            can_intake_patient_lookup=True,
        )
        assigned_patient = Patient.objects.create(
            uhid="ASSIGNED-INTAKE",
            first_name="Assigned",
            last_name="Patient",
            phone_number="9123456782",
            created_by=self.owner,
        )
        assigned_case = self.create_case(uhid="ASSIGNED-INTAKE-CASE", patient=assigned_patient)
        self.assign_case(assigned_case, self.other)
        hidden_patient = Patient.objects.create(
            uhid="UNASSIGNED-INTAKE",
            first_name="Unassigned",
            last_name="Patient",
            phone_number="9123456783",
            created_by=self.owner,
        )

        from .intake_access import resolve_case_intake_patient

        self.assertIsNotNone(resolve_case_intake_patient(actor=self.other, patient_id=assigned_patient.pk))
        self.assertIsNone(resolve_case_intake_patient(actor=self.other, patient_id=hidden_patient.pk))
        role = RoleSetting.objects.get(role_name="Assigned Intake")
        role.case_data_scope = CaseDataScope.ALL
        role.save(update_fields=["case_data_scope"])
        self.assertIsNotNone(resolve_case_intake_patient(actor=self.other, patient_id=hidden_patient.pk))

    def test_intake_permission_is_rechecked_after_form_validation(self):
        self.add_role(
            self.other,
            name="TOCTOU Intake",
            case_data_scope=CaseDataScope.ALL,
            can_case_create=True,
            can_intake_patient_lookup=True,
        )
        patient = Patient.objects.create(
            uhid="TOCTOU-INTAKE",
            first_name="TOCTOU",
            last_name="Patient",
            age=40,
            phone_number="9123456784",
            created_by=self.owner,
        )
        form = CaseForm(data=self._payload(patient), actor=self.other)
        self.assertTrue(form.is_valid(), form.errors)
        RoleSetting.objects.filter(role_name="TOCTOU Intake").update(can_intake_patient_lookup=False)

        with self.assertRaises(ValidationError), transaction.atomic():
            form.revalidate_intake_selection(lock=True)


class PatientEditPersistenceTests(SecurityFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username="patient-edit-admin",
            password="strong-password-123",
            email="patient-edit@example.invalid",
        )
        self.patient = Patient.objects.create(
            uhid="EDIT-PERSIST",
            prefix="MR",
            first_name="Before",
            last_name="Patient",
            gender="MALE",
            age=40,
            phone_number="9234567890",
            created_by=self.admin,
        )
        self.client.force_login(self.admin)

    def _payload(self, **changes):
        payload = {
            "uhid": self.patient.uhid,
            "prefix": "MR",
            "first_name": self.patient.first_name,
            "last_name": self.patient.last_name,
            "gender": "MALE",
            "blood_group": "",
            "date_of_birth": "",
            "place": "",
            "age": "40",
            "phone_number": "9234567890",
            "alternate_phone_number": "",
        }
        payload.update(changes)
        return payload

    def test_successful_edit_persists_exact_change_and_audits_after_write(self):
        response = self.client.post(
            reverse("patients:patient_edit", kwargs={"pk": self.patient.pk}),
            self._payload(first_name="After"),
        )
        self.assertEqual(response.status_code, 302)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.first_name, "After")
        event = AuditEvent.objects.get(action="patient.identity_updated", object_id=str(self.patient.pk))
        self.assertIn("first_name", event.metadata["changed_fields"])

    def test_noop_and_failed_validation_emit_no_success_audit(self):
        noop = self.client.post(
            reverse("patients:patient_edit", kwargs={"pk": self.patient.pk}),
            self._payload(),
        )
        invalid = self.client.post(
            reverse("patients:patient_edit", kwargs={"pk": self.patient.pk}),
            self._payload(phone_number="not-a-phone"),
        )
        self.assertEqual(noop.status_code, 302)
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(AuditEvent.objects.filter(action="patient.identity_updated").exists())

    def test_forced_audit_failure_rolls_back_patient_edit(self):
        with patch("patients.views.record_audit_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("patients:patient_edit", kwargs={"pk": self.patient.pk}),
                    self._payload(first_name="Must Roll Back"),
                )
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.first_name, "Before")


class PatientMergeRecoveryTests(SecurityFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username="merge-recovery-admin",
            password="strong-password-123",
            email="merge-recovery@example.invalid",
        )

    def _merged_fixture(self):
        source = Patient.objects.create(
            uhid=f"REC-SOURCE-{Patient.objects.count()}",
            first_name="Recovery",
            last_name="Source",
            phone_number="9345678901",
            created_by=self.admin,
        )
        target = Patient.objects.create(
            uhid=f"REC-TARGET-{Patient.objects.count()}",
            first_name="Recovery",
            last_name="Target",
            phone_number="9345678902",
            created_by=self.admin,
        )
        case = self.create_case(uhid=f"REC-CASE-{Case.objects.count()}", patient=source, created_by=self.admin)
        _merge_patient_records(source_patient=source, target_patient=target, actor=self.admin)
        return source, target, case, PatientMergeRecovery.objects.get(source_patient=source)

    def test_happy_path_restores_only_recorded_cases_and_consumes_evidence(self):
        source, target, case, recovery = self._merged_fixture()

        self.assertEqual(recover_patient_merge(recovery_id=recovery.recovery_id, actor=self.admin), 1)

        source.refresh_from_db()
        case.refresh_from_db()
        recovery.refresh_from_db()
        self.assertIsNone(source.merged_into_id)
        self.assertEqual(case.patient_id, source.pk)
        self.assertIsNotNone(recovery.consumed_at)
        self.assertTrue(AuditEvent.objects.filter(action="patient.merge_recovered").exists())
        with self.assertRaises(ValidationError):
            recover_patient_merge(recovery_id=recovery.recovery_id, actor=self.admin)

    def test_expired_tampered_moved_and_unauthorized_recoveries_fail_closed(self):
        source, target, case, recovery = self._merged_fixture()
        expired_recovery = PatientMergeRecovery.objects.create(
            source_patient=source,
            target_patient=target,
            moved_case_ids=[case.pk],
            merge_audit_event=recovery.merge_audit_event,
            merge_request_id="expired-test-record",
            created_by=self.admin,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        with self.assertRaises(ValidationError):
            recover_patient_merge(recovery_id=expired_recovery.recovery_id, actor=self.admin)

        source, target, case, recovery = self._merged_fixture()
        other = Patient.objects.create(
            uhid="REC-OTHER",
            first_name="Other",
            last_name="Patient",
            phone_number="9345678903",
            created_by=self.admin,
        )
        Case.objects.filter(pk=case.pk).update(patient=other)
        with self.assertRaises(ValidationError):
            recover_patient_merge(recovery_id=recovery.recovery_id, actor=self.admin)

        source, target, case, recovery = self._merged_fixture()
        with self.assertRaises(Exception):
            PatientMergeRecovery.objects.filter(pk=recovery.pk).update(moved_case_ids=[])
        with self.assertRaises(Exception):
            recover_patient_merge(recovery_id=recovery.recovery_id, actor=self.other)

    def test_forced_recovery_audit_failure_rolls_back_all_changes(self):
        source, target, case, recovery = self._merged_fixture()
        with patch("patients.merge_recovery.record_audit_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                recover_patient_merge(recovery_id=recovery.recovery_id, actor=self.admin)

        source.refresh_from_db()
        case.refresh_from_db()
        recovery.refresh_from_db()
        self.assertEqual(source.merged_into_id, target.pk)
        self.assertEqual(case.patient_id, target.pk)
        self.assertIsNone(recovery.consumed_at)

    def test_management_command_requires_dry_run_or_exact_typed_confirmation(self):
        source, target, case, recovery = self._merged_fixture()
        output = io.StringIO()

        call_command(
            "recover_patient_merge",
            str(recovery.recovery_id),
            "--actor",
            self.admin.username,
            "--dry-run",
            stdout=output,
        )
        recovery.refresh_from_db()
        self.assertIsNone(recovery.consumed_at)
        self.assertNotIn(source.first_name, output.getvalue())
        self.assertNotIn(source.phone_number, output.getvalue())

        with self.assertRaises(CommandError):
            call_command(
                "recover_patient_merge",
                str(recovery.recovery_id),
                "--actor",
                self.admin.username,
                "--confirm",
                "RECOVER MERGE wrong-id",
            )

        call_command(
            "recover_patient_merge",
            str(recovery.recovery_id),
            "--actor",
            self.admin.username,
            "--confirm",
            f"RECOVER MERGE {recovery.recovery_id}",
            stdout=io.StringIO(),
        )
        recovery.refresh_from_db()
        self.assertIsNotNone(recovery.consumed_at)


class MandatoryAuditRollbackTests(SecurityFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def test_representative_iam_and_clinical_writes_roll_back_when_audit_fails(self):
        role = RoleSetting.objects.create(role_name="Audit Rollback Role")
        patient = Patient.objects.create(
            uhid="AUDIT-ROLLBACK",
            first_name="Audit",
            last_name="Rollback",
            phone_number="9456789012",
            created_by=self.owner,
        )
        case = self.create_case(uhid="AUDIT-ROLLBACK-CASE", patient=patient)
        task = Task.objects.create(
            case=case,
            title="Original task",
            due_date=timezone.localdate(),
            created_by=self.owner,
        )
        vital = VitalEntry.objects.create(case=case, spo2=98, created_by=self.owner, updated_by=self.owner)

        mutations = [
            (self.owner, "first_name", "Changed", ""),
            (role, "can_case_create", True, False),
            (patient, "first_name", "Changed", "Audit"),
            (case, "diagnosis", "Changed", ""),
            (task, "title", "Changed", "Original task"),
            (vital, "spo2", 99, 98),
        ]
        for instance, field, changed, original in mutations:
            setattr(instance, field, changed)
            with patch("patients.signals.record_audit_event", side_effect=RuntimeError("audit unavailable")):
                with self.assertRaises(RuntimeError):
                    instance.save(update_fields=[field])
            instance.refresh_from_db()
            self.assertEqual(getattr(instance, field), original)

    def test_clinical_delete_rolls_back_when_delete_audit_fails(self):
        case = self.create_case(uhid="AUDIT-DELETE")
        case_id = case.pk
        with patch("patients.signals.record_audit_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                case.delete()
        self.assertTrue(Case.objects.filter(pk=case_id).exists())


class DataOperationAuditBoundaryTests(SecurityFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username="data-audit-admin",
            password="strong-password-123",
            email="data-audit@example.invalid",
        )
        self.client.force_login(self.admin)

    def test_import_domain_writes_roll_back_when_success_audit_fails(self):
        from .audit import record_audit_event as real_record_audit_event

        def fake_import(_archive_bytes):
            Patient.objects.create(
                uhid="IMPORT-MUST-ROLLBACK",
                first_name="Import",
                last_name="Rollback",
                phone_number="9567890123",
                created_by=self.admin,
            )
            return {
                "counts": {"cases": 1},
                "safety_backup_path": "test-only-safety-backup.zip",
            }

        def fail_success_event(*args, **kwargs):
            if kwargs.get("action") == "patient_data.imported":
                raise RuntimeError("audit unavailable")
            return real_record_audit_event(*args, **kwargs)

        upload = SimpleUploadedFile("bundle.zip", b"test bundle", content_type="application/zip")
        with patch("patients.views.database_bundle.import_bundle_bytes", side_effect=fake_import), patch(
            "patients.views.record_audit_event",
            side_effect=fail_success_event,
        ):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "import",
                    "confirm_phrase": "REPLACE PATIENT DATA",
                    "bundle_file": upload,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Patient.objects.filter(uhid="IMPORT-MUST-ROLLBACK").exists())
        self.assertTrue(AuditEvent.objects.filter(action="patient_data.import_failed").exists())

    def test_export_fails_before_returning_bundle_when_audit_cannot_persist(self):
        with patch("patients.views.database_bundle.create_bundle_archive", return_value=(b"secret archive", {}, "x.zip")), patch(
            "patients.views.record_audit_event",
            side_effect=RuntimeError("audit unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("patients:settings_database"), {"action": "export"})

    def test_permanent_delete_rolls_back_when_mandatory_audit_fails(self):
        case = self.create_case(uhid="DELETE-AUDIT-ROLLBACK", created_by=self.admin)
        self.client.post(
            reverse("patients:settings_case_management"),
            {"action": "request_delete", "case_id": case.pk},
        )
        with patch("patients.views.record_audit_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("patients:settings_case_management"),
                    {"action": "delete_case", "case_id": case.pk},
                )
        self.assertTrue(Case.objects.filter(pk=case.pk).exists())


@skipUnless(connection.vendor == "postgresql", "Concurrent allocator and merge locks require PostgreSQL.")
class PostgreSQLConcurrencySecurityTests(SecurityFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def test_temporary_uhid_allocator_is_unique_under_concurrency(self):
        barrier = Barrier(8)

        def allocate():
            close_old_connections()
            try:
                barrier.wait()
                return generate_temporary_patient_uhid(today=timezone.localdate())
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=8) as executor:
            allocated = list(executor.map(lambda _: allocate(), range(8)))

        self.assertEqual(len(set(allocated)), 8)
        self.assertEqual(sorted(int(value.rsplit("-", 1)[1]) for value in allocated), list(range(1, 9)))

    def test_concurrent_merges_cannot_create_a_patient_chain(self):
        actor = User.objects.create_superuser(
            username="merge-lock-admin",
            password="strong-password-123",
            email="merge@example.invalid",
        )
        patients = [
            Patient.objects.create(
                uhid=f"LOCK-{index}",
                first_name="Lock",
                last_name=str(index),
                phone_number=f"90000000{index:02d}",
                created_by=actor,
            )
            for index in range(3)
        ]
        barrier = Barrier(2)

        def merge(source_id, target_id):
            close_old_connections()
            try:
                barrier.wait()
                source = Patient.objects.get(pk=source_id)
                target = Patient.objects.get(pk=target_id)
                _merge_patient_records(source_patient=source, target_patient=target, actor=actor)
                return "merged"
            except (ValidationError, IntegrityError):
                return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda pair: merge(*pair),
                    [(patients[0].pk, patients[1].pk), (patients[1].pk, patients[2].pk)],
                )
            )

        self.assertEqual(sorted(results), ["merged", "rejected"])
        self.assertFalse(Patient.objects.filter(merged_into__merged_into__isnull=False).exists())

    @override_settings(AUTH_THROTTLE_ACCOUNT_LIMIT=20, AUTH_THROTTLE_IP_LIMIT=3)
    def test_auth_ip_throttle_serializes_concurrent_random_identifiers(self):
        barrier = Barrier(8)

        def consume(index):
            close_old_connections()
            try:
                request = RequestFactory().post("/api/auth/token/", REMOTE_ADDR="203.0.113.80")
                barrier.wait()
                return consume_auth_attempt(
                    scope="jwt",
                    request=request,
                    identifier=f"random-concurrent-{index}",
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(consume, range(8)))

        ip_bucket = AuthenticationThrottleBucket.objects.get(scope="jwt:ip")
        self.assertEqual(ip_bucket.failure_count, 3)
        self.assertIsNotNone(ip_bucket.blocked_until)
        self.assertGreaterEqual(sum(result > 0 for result in results), 5)
        self.assertLessEqual(AuthenticationThrottleBucket.objects.filter(scope="jwt:account").count(), 3)

    def test_merge_serializes_stale_direct_case_save_and_preserves_terminal_source(self):
        actor = User.objects.create_superuser(
            username="merge-case-race-admin",
            password="strong-password-123",
            email="merge-case-race@example.invalid",
        )
        source = Patient.objects.create(
            uhid="MERGE-RACE-SOURCE",
            first_name="Race",
            last_name="Source",
            phone_number="9678901234",
            created_by=actor,
        )
        target = Patient.objects.create(
            uhid="MERGE-RACE-TARGET",
            first_name="Race",
            last_name="Target",
            phone_number="9678901235",
            created_by=actor,
        )
        existing_case = self.create_case(
            uhid="MERGE-RACE-EXISTING",
            patient=source,
            created_by=actor,
        )
        stale_source = Patient.objects.get(pk=source.pk)
        merge_locked = Event()
        case_started = Event()
        case_backend_pid = {}
        real_record_audit_event = record_audit_event

        def merge_audit_hook(*args, **kwargs):
            if kwargs.get("action") == "patient.merged":
                merge_locked.set()
                if not case_started.wait(5):
                    raise RuntimeError("Concurrent case write did not start.")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                            [case_backend_pid["pid"]],
                        )
                        row = cursor.fetchone()
                    if row and row[0] == "Lock":
                        break
                    time.sleep(0.01)
                else:
                    raise RuntimeError("Concurrent case write never waited on the patient lock.")
            return real_record_audit_event(*args, **kwargs)

        def merge_worker():
            close_old_connections()
            try:
                with patch("patients.views.record_audit_event", side_effect=merge_audit_hook):
                    _merge_patient_records(
                        source_patient=Patient.objects.get(pk=source.pk),
                        target_patient=Patient.objects.get(pk=target.pk),
                        actor=actor,
                    )
                return "merged"
            finally:
                close_old_connections()

        def case_worker():
            close_old_connections()
            try:
                if not merge_locked.wait(5):
                    return "merge-not-locked"
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    case_backend_pid["pid"] = cursor.fetchone()[0]
                case_started.set()
                with transaction.atomic():
                    Case.objects.create(
                        patient=stale_source,
                        uhid=stale_source.uhid,
                        first_name=stale_source.first_name,
                        last_name=stale_source.last_name,
                        phone_number=stale_source.phone_number,
                        category=self.category,
                        created_by=actor,
                    )
                return "created"
            except ValidationError:
                return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            merge_future = executor.submit(merge_worker)
            case_future = executor.submit(case_worker)
            self.assertEqual(merge_future.result(timeout=10), "merged")
            self.assertEqual(case_future.result(timeout=10), "rejected")

        source.refresh_from_db()
        existing_case.refresh_from_db()
        self.assertEqual(source.merged_into_id, target.pk)
        self.assertEqual(existing_case.patient_id, target.pk)
        self.assertEqual(Case.objects.filter(patient=source).count(), 0)

    def test_database_trigger_rejects_bulk_case_attachment_to_merged_source(self):
        actor = User.objects.create_superuser(
            username="merge-trigger-admin",
            password="strong-password-123",
            email="merge-trigger@example.invalid",
        )
        source = Patient.objects.create(
            uhid="TRIGGER-MERGED-SOURCE",
            first_name="Trigger",
            last_name="Source",
            phone_number="9678901236",
            created_by=actor,
        )
        target = Patient.objects.create(
            uhid="TRIGGER-MERGED-TARGET",
            first_name="Trigger",
            last_name="Target",
            phone_number="9678901237",
            created_by=actor,
        )
        _merge_patient_records(source_patient=source, target_patient=target, actor=actor)
        target_case = self.create_case(uhid="TRIGGER-TARGET-CASE", patient=target, created_by=actor)

        with self.assertRaises(Exception), transaction.atomic():
            Case.objects.filter(pk=target_case.pk).update(patient=source)

        target_case.refresh_from_db()
        self.assertEqual(target_case.patient_id, target.pk)

    def test_concurrent_merge_recovery_is_one_time(self):
        actor = User.objects.create_superuser(
            username="recovery-race-admin",
            password="strong-password-123",
            email="recovery-race@example.invalid",
        )
        source = Patient.objects.create(
            uhid="RECOVERY-RACE-SOURCE",
            first_name="Recovery",
            last_name="Race Source",
            phone_number="9678901238",
            created_by=actor,
        )
        target = Patient.objects.create(
            uhid="RECOVERY-RACE-TARGET",
            first_name="Recovery",
            last_name="Race Target",
            phone_number="9678901239",
            created_by=actor,
        )
        self.create_case(uhid="RECOVERY-RACE-CASE", patient=source, created_by=actor)
        _merge_patient_records(source_patient=source, target_patient=target, actor=actor)
        recovery = PatientMergeRecovery.objects.get(source_patient=source)
        barrier = Barrier(2)

        def recover():
            close_old_connections()
            try:
                barrier.wait()
                recover_patient_merge(recovery_id=recovery.recovery_id, actor=actor)
                return "recovered"
            except ValidationError:
                return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: recover(), range(2)))

        self.assertEqual(sorted(results), ["recovered", "rejected"])
        self.assertEqual(
            AuditEvent.objects.filter(
                action="patient.merge_recovered",
                object_id=str(recovery.recovery_id),
            ).count(),
            1,
        )

    def test_concurrent_patient_edits_preserve_distinct_changed_fields(self):
        actor = User.objects.create_superuser(
            username="patient-edit-race-admin",
            password="strong-password-123",
            email="patient-edit-race@example.invalid",
        )
        patient = Patient.objects.create(
            uhid="EDIT-RACE",
            prefix="MR",
            first_name="BeforeFirst",
            last_name="BeforeLast",
            gender="MALE",
            age=40,
            phone_number="9789012345",
            created_by=actor,
        )
        clients = [AuthVersionTestClient(), AuthVersionTestClient()]
        for client in clients:
            client.force_login(actor)
        validation_barrier = Barrier(2)
        real_is_valid = PatientForm.is_valid

        def synchronized_is_valid(form):
            validation_barrier.wait()
            return real_is_valid(form)

        base_payload = {
            "uhid": patient.uhid,
            "prefix": "MR",
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "gender": "MALE",
            "blood_group": "",
            "date_of_birth": "",
            "place": "",
            "age": "40",
            "phone_number": patient.phone_number,
            "alternate_phone_number": "",
        }

        def edit(index):
            close_old_connections()
            try:
                payload = dict(base_payload)
                if index == 0:
                    payload["first_name"] = "AfterFirst"
                else:
                    payload["last_name"] = "AfterLast"
                return clients[index].post(
                    reverse("patients:patient_edit", kwargs={"pk": patient.pk}),
                    payload,
                ).status_code
            finally:
                close_old_connections()

        with patch("patients.forms.PatientForm.is_valid", new=synchronized_is_valid):
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(edit, range(2)))

        patient.refresh_from_db()
        self.assertEqual(statuses, [302, 302])
        self.assertEqual(patient.first_name, "Afterfirst")
        self.assertEqual(patient.last_name, "Afterlast")

    def test_postgresql_trigger_rejects_merge_recovery_tamper_and_delete(self):
        actor = User.objects.create_superuser(
            username="recovery-trigger-admin",
            password="strong-password-123",
            email="recovery-trigger@example.invalid",
        )
        source = Patient.objects.create(
            uhid="RECOVERY-TRIGGER-SOURCE",
            first_name="Recovery",
            last_name="Trigger Source",
            phone_number="9789012346",
            created_by=actor,
        )
        target = Patient.objects.create(
            uhid="RECOVERY-TRIGGER-TARGET",
            first_name="Recovery",
            last_name="Trigger Target",
            phone_number="9789012347",
            created_by=actor,
        )
        self.create_case(uhid="RECOVERY-TRIGGER-CASE", patient=source, created_by=actor)
        _merge_patient_records(source_patient=source, target_patient=target, actor=actor)
        recovery = PatientMergeRecovery.objects.get(source_patient=source)

        with self.assertRaises(Exception), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE patients_patientmergerecovery SET moved_case_ids = %s WHERE id = %s",
                ["[]", recovery.pk],
            )
        with self.assertRaises(Exception), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM patients_patientmergerecovery WHERE id = %s",
                [recovery.pk],
            )

    def test_postgresql_trigger_rejects_direct_audit_update(self):
        event = AuditEvent.objects.create(category=AuditEvent.Category.IAM, action="trigger.test")
        with self.assertRaises(Exception), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE patients_auditevent SET action = %s WHERE id = %s", ["tampered", event.pk])
