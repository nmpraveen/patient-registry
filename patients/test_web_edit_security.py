"""Revalidate web session identity at the clinical mutation lock boundary."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import HASH_SESSION_KEY, get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection, connections, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .auth_security import (
    AUTH_VERSION_SESSION_KEY, DEVICE_CREDENTIAL_SESSION_KEY, bump_auth_version, current_auth_version,
)
from .models import (
    Case, DepartmentConfig, DeviceApprovalPolicy, StaffDeviceCredential,
    StaffDeviceCredentialStatus, Task, TaskStatus,
)
from .recent_cases import notes_baseline
from .task_editing import lock_edit_actor, lock_web_edit_actor, task_edit_token
from .test_client import AuthVersionTestClient


class WebEditFixture:
    client_class = AuthVersionTestClient

    def setUp(self):
        self.user = get_user_model().objects.create_superuser("web-review", password="synthetic-only")
        self.client.force_login(self.user)
        category, _ = DepartmentConfig.objects.get_or_create(name="MEDICINE")
        self.case = Case.objects.create(first_name="Synthetic", last_name="Web review", uhid="REVIEW-WEB",
            phone_number="9999999999", category=category, created_by=self.user, notes="Original")
        self.task = Task.objects.create(case=self.case, title="Synthetic web task",
            due_date=timezone.localdate(), assigned_user=self.user, created_by=self.user)

    def request(self):
        request = RequestFactory().post("/patients/")
        request.user = self.user
        request.session = self.client.session
        return request


class WebEditSecurityTests(WebEditFixture, TestCase):
    def test_current_session_is_accepted_but_invalid_bindings_are_rejected(self):
        self.assertEqual(lock_web_edit_actor(self.request()).pk, self.user.pk)
        for invalid in (None, True, "1", 0, -1, current_auth_version(self.user) + 1):
            with self.subTest(version=invalid):
                request = self.request()
                request.session[AUTH_VERSION_SESSION_KEY] = invalid
                with self.assertRaises(PermissionDenied):
                    lock_web_edit_actor(request)
        for invalid in (None, "", "stale-password-hash", 1):
            with self.subTest(session_hash=invalid):
                request = self.request()
                request.session[HASH_SESSION_KEY] = invalid
                with self.assertRaises(PermissionDenied):
                    lock_web_edit_actor(request)

    def test_fresh_active_and_password_state_are_checked_independently_of_version(self):
        request = self.request()
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            lock_web_edit_actor(request)
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=True)
        new_password = get_user_model()(username="synthetic-other")
        new_password.set_password("different-synthetic-password")
        # Direct SQL deliberately avoids the normal auth-version signal.
        get_user_model().objects.filter(pk=self.user.pk).update(password=new_password.password)
        with self.assertRaises(PermissionDenied):
            lock_web_edit_actor(request)

    def test_approved_device_is_rechecked_even_without_version_bump(self):
        policy = DeviceApprovalPolicy.get_solo()
        policy.enabled = True
        policy.save()
        policy.target_users.add(self.user)
        credential = StaffDeviceCredential.objects.create(user=self.user, device_label="Synthetic",
            credential_id="synthetic-web-review", public_key="synthetic-public-key",
            status=StaffDeviceCredentialStatus.APPROVED)
        self.client.force_login(self.user)
        request = self.request()
        request.session[DEVICE_CREDENTIAL_SESSION_KEY] = credential.pk
        self.assertEqual(lock_web_edit_actor(request).pk, self.user.pk)
        StaffDeviceCredential.objects.filter(pk=credential.pk).update(status=StaffDeviceCredentialStatus.REVOKED)
        with self.assertRaises(PermissionDenied):
            lock_web_edit_actor(request)

    def test_quick_mutations_and_recent_notes_reject_revocation_after_middleware(self):
        routes = [
            ("task_quick_complete", self.task.pk, {}),
            ("task_quick_reopen", self.task.pk, {}),
            ("task_quick_reschedule", self.task.pk, {"due_date": timezone.localdate().isoformat()}),
            ("task_quick_note", self.task.pk, {"note": "Discard"}),
            ("recent_case_update", self.case.pk, {"notes": "Discard", "notes_baseline": notes_baseline(self.case, self.user)}),
        ]

        def revoke(actor):
            bump_auth_version(actor, reason="synthetic-post-middleware-revocation")
            return lock_edit_actor(actor)

        for route, pk, data in routes:
            with self.subTest(route=route):
                self.client.force_login(self.user)
                with patch("patients.task_editing.lock_edit_actor", side_effect=revoke):
                    response = self.client.post(reverse("patients:" + route, args=[pk]),
                        {"edit_baseline": task_edit_token(self.task, self.user), **data})
                self.assertEqual(response.status_code, 403)
        self.case.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.case.notes, "Original")
        self.assertEqual((self.task.status, self.task.notes), (TaskStatus.SCHEDULED, ""))
        self.assertFalse(self.case.activity_logs.exists())


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL independent transactions.")
class WebEditConcurrencyTests(WebEditFixture, TransactionTestCase):
    def test_committed_session_revocation_before_actor_lock_prevents_write(self):
        authenticated, resume = Event(), Event()
        client = self.client
        token = task_edit_token(self.task, self.user)

        def wait_before_lock(actor):
            authenticated.set()
            if not resume.wait(5):
                raise AssertionError("Timed out waiting for committed session revocation")
            return lock_edit_actor(actor)

        def write():
            close_old_connections()
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                return client.post(reverse("patients:task_quick_complete", args=[self.task.pk]), {"edit_baseline": token})
            finally:
                connections["default"].close()

        with patch("patients.task_editing.lock_edit_actor", side_effect=wait_before_lock):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(write)
                try:
                    self.assertTrue(authenticated.wait(5))
                    with transaction.atomic():
                        bump_auth_version(self.user, reason="synthetic-committed-web-revocation")
                finally:
                    resume.set()
                response = future.result(timeout=10)
        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SCHEDULED)
        self.assertFalse(self.case.activity_logs.exists())
