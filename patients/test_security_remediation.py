from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
from threading import Barrier
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .audit import record_audit_event
from .forms import UserManagementCreateForm, UserManagementUpdateForm
from .models import (
    AuditEvent,
    Case,
    CaseDataScope,
    DepartmentConfig,
    DeviceApprovalPolicy,
    Patient,
    RoleSetting,
    StaffDeviceCredential,
    StaffDeviceCredentialStatus,
    Task,
    TaskStatus,
    TaskType,
    VitalEntry,
    generate_temporary_patient_uhid,
)
from .views import _accessible_case_queryset, _merge_patient_records, _patient_search_queryset


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
            {"target_patient": target.pk},
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

    def test_postgresql_trigger_rejects_direct_audit_update(self):
        event = AuditEvent.objects.create(category=AuditEvent.Category.IAM, action="trigger.test")
        with self.assertRaises(Exception), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE patients_auditevent SET action = %s WHERE id = %s", ["tampered", event.pk])
