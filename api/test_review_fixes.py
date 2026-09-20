"""Security interleavings and bounded response work from the September review."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Event
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import RequestFactory, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from patients.auth_security import bump_auth_version, clear_auth_attempts, consume_auth_attempt, current_auth_version
from patients.models import (
    AuthenticationThrottleBucket, Case, DepartmentConfig, DeviceApprovalPolicy,
    StaffDeviceCredentialStatus, StaffMobileDeviceCredential, Task, TaskStatus, VitalEntry,
)
from patients.task_editing import lock_edit_actor

from . import views
from .models import MobileDeviceToken, MobileNotification, MobileNotificationType, MobileWriteReceipt
from .notifications import authorized_notification_queryset, purge_stale_notifications_for_user, suspend_mobile_notifications
from .token_views import AuthVersionTokenObtainPairSerializer, AuthVersionTokenObtainPairView, AuthVersionTokenRefreshView


class ReviewFixture:
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="review-security", password="synthetic-password")
        self.category, _ = DepartmentConfig.objects.get_or_create(name="MEDICINE")
        self.case = Case.objects.create(
            uhid="REVIEW-SYNTHETIC", first_name="Synthetic", last_name="Review", phone_number="9999999999",
            category=self.category, created_by=self.user,
        )
        self.task = Task.objects.create(case=self.case, title="Synthetic review task", due_date=timezone.localdate(),
                                       assigned_user=self.user, created_by=self.user)
        self.access = AuthVersionTokenObtainPairSerializer.get_token(self.user).access_token
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")


class ReviewSecurityTests(ReviewFixture, APITestCase):
    def revoke_before_lock(self, actor):
        bump_auth_version(actor, reason="synthetic-interleaved-revocation")
        return lock_edit_actor(actor)

    def test_mutation_paths_revalidate_the_original_token_after_lock_wait(self):
        requests = [
            ("task_complete", [self.task.pk], {}),
            ("task_complete", [self.task.pk], {"client_write_id": "review-complete"}),
            ("task_note", [self.task.pk], {"note": "New synthetic note"}),
            ("case_vitals", [self.case.pk], {"client_write_id": "review-vital", "pr": 80}),
            ("case_call_outcome", [self.case.pk], {"client_write_id": "review-call", "outcome": "no_answer"}),
            ("devices", [], {"token": "synthetic-review-device"}),
        ]
        initial_activities = self.case.activity_logs.count()
        for name, args, data in requests:
            with self.subTest(name=name, data=data):
                # The transaction rolls back this synthetic revocation on denial.
                # The PostgreSQL test below uses an independent committed revoke.
                with patch("api.views.lock_edit_actor", side_effect=self.revoke_before_lock):
                    response = self.client.post(reverse(f"api:{name}", args=args), data, format="json")
                self.assertEqual(response.status_code, 401, response.content)
                self.task.refresh_from_db()
                self.assertEqual(self.task.status, TaskStatus.SCHEDULED)
                self.assertEqual(self.task.notes, "")
                self.assertEqual(self.case.activity_logs.count(), initial_activities)
                self.assertFalse(self.case.vitals.exists())
                self.assertFalse(self.case.call_logs.exists())
                self.assertFalse(MobileWriteReceipt.objects.exists())
                self.assertFalse(MobileDeviceToken.objects.exists())

    def test_existing_receipt_replay_revalidates_the_token(self):
        url = reverse("api:task_complete", args=[self.task.pk])
        data = {"client_write_id": "review-applied"}
        self.assertEqual(self.client.post(url, data, format="json").status_code, 200)
        initial_activities = self.case.activity_logs.count()
        with patch("api.views.lock_edit_actor", side_effect=self.revoke_before_lock):
            response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(MobileWriteReceipt.objects.count(), 1)
        self.assertEqual(self.case.activity_logs.count(), initial_activities)

    def test_device_status_is_rechecked_even_without_an_auth_version_change(self):
        policy = DeviceApprovalPolicy.get_solo()
        policy.enabled = True
        policy.save()
        policy.target_users.add(self.user)
        credential = StaffMobileDeviceCredential(user=self.user, status=StaffDeviceCredentialStatus.APPROVED)
        credential.set_secret("synthetic-device-secret")
        credential.save()
        access = AuthVersionTokenObtainPairSerializer.get_token(self.user).access_token
        access["mobile_device_id"] = str(credential.device_id)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        def revoke_device(actor):
            StaffMobileDeviceCredential.objects.filter(pk=credential.pk).update(status=StaffDeviceCredentialStatus.REVOKED)
            return lock_edit_actor(actor)

        with patch("api.views.lock_edit_actor", side_effect=revoke_device):
            response = self.client.post(reverse("api:task_complete", args=[self.task.pk]), {}, format="json")
        self.assertEqual(response.status_code, 401)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SCHEDULED)

    def test_malformed_notification_cursor_always_returns_400(self):
        for cursor in ("é" * 40, "a" * 20 + " " + "b" * 20, "." * 40, "a" * 129, "short", "a" * 40):
            with self.subTest(cursor=cursor):
                response = self.client.get(reverse("api:notifications"), {"cursor": cursor})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "invalid_cursor")


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks and independent transactions.")
class ReviewConcurrencyTests(ReviewFixture, TransactionTestCase):
    def test_committed_revocation_after_jwt_authentication_prevents_clinical_write(self):
        authenticated, resume = Event(), Event()
        initial_version = current_auth_version(self.user)

        def wait_before_lock(actor):
            authenticated.set()
            if not resume.wait(5):
                raise AssertionError("Timed out waiting for the security change")
            return lock_edit_actor(actor)

        def write():
            close_old_connections()
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
                return client.post(reverse("api:task_complete", args=[self.task.pk]),
                                   {"client_write_id": "concurrent-revocation"}, format="json")
            finally:
                connections["default"].close()

        with patch("api.views.lock_edit_actor", side_effect=wait_before_lock):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(write)
                try:
                    self.assertTrue(authenticated.wait(5))
                    bump_auth_version(self.user, reason="concurrent-committed-revocation")
                finally:
                    resume.set()
                response = future.result(timeout=10)
        self.assertEqual(current_auth_version(self.user), initial_version + 1)
        self.assertEqual(response.status_code, 401, response.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SCHEDULED)
        self.assertFalse(MobileWriteReceipt.objects.exists())
        self.assertFalse(self.case.activity_logs.exists())

    def test_jwt_reservation_and_success_clear_do_not_deadlock(self):
        for view in (AuthVersionTokenObtainPairView, AuthVersionTokenRefreshView):
            self.assertIn("default", view.as_view()._non_atomic_requests)
        request = RequestFactory().post("/api/auth/token/", REMOTE_ADDR="192.0.2.30")
        kwargs = {"scope": "jwt", "request": request, "identifier": "synthetic-throttle"}
        self.assertEqual(consume_auth_attempt(**kwargs), 0)
        clear_locked, consumer_started, consumer_ip_locked = Event(), Event(), Event()

        def clear_hook(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if '"patients_authenticationthrottlebucket"' in sql and "FOR UPDATE" in sql and not clear_locked.is_set():
                clear_locked.set()
                self.assertTrue(consumer_started.wait(5))
                # With correct ordering the consumer waits on our IP lock.
                # With reversed ordering it obtains IP; the subsequent account
                # and IP requests would form the production deadlock cycle.
                consumer_ip_locked.wait(0.25)
            return result

        def consumer_hook(execute, sql, params, many, context):
            is_lock = '"patients_authenticationthrottlebucket"' in sql and "FOR UPDATE" in sql
            if is_lock and not consumer_started.is_set():
                consumer_started.set()
            result = execute(sql, params, many, context)
            if is_lock and not consumer_ip_locked.is_set():
                consumer_ip_locked.set()
            return result

        def run(operation, hook, wait=False):
            close_old_connections()
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '3s'")
                if wait:
                    self.assertTrue(clear_locked.wait(5))
                with connections["default"].execute_wrapper(hook):
                    return operation(**kwargs)
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            clearing = executor.submit(run, clear_auth_attempts, clear_hook)
            consuming = executor.submit(run, consume_auth_attempt, consumer_hook, True)
            clearing.result(timeout=10)
            self.assertEqual(consuming.result(timeout=10), 0)
        buckets = dict(AuthenticationThrottleBucket.objects.filter(scope__startswith="jwt:")
                       .values_list("scope", "failure_count"))
        self.assertEqual(buckets, {"jwt:ip": 1, "jwt:account": 1})


class ReviewResponseBoundsTests(ReviewFixture, APITestCase):
    def test_current_demographic_age_uses_dob_without_changing_edit_baseline(self):
        born = date(timezone.localdate().year - 40, 1, 1)
        Case.objects.filter(pk=self.case.pk).update(date_of_birth=born, age=25)
        self.case.refresh_from_db()
        listing = self.client.get(reverse("api:case_list"), {"bucket": "all", "assigned_to": "all"})
        search = self.client.post(reverse("api:case_search"),
                                  {"query": "Synthetic", "bucket": "all", "assigned_to": "all"}, format="json")
        for response in (listing, search):
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["results"][0]["age"], 40)
        self.assertEqual(views._mobile_case_payload(self.case, user=self.user)["age"], 40)
        self.assertEqual(views._case_edit_payload(self.case)["age"], 25)

    def test_list_search_and_write_summaries_bound_related_objects_and_keep_counts(self):
        today = timezone.localdate()
        tasks = [
            Task(case=self.case, title="Old completed", due_date=today - timedelta(days=60), status=TaskStatus.COMPLETED)
            for _ in range(100)
        ] + [
            Task(case=self.case, title="Cancelled", due_date=today, status=TaskStatus.CANCELLED),
            Task(case=self.case, title="Upcoming", due_date=today + timedelta(days=2)),
            Task(case=self.case, title="First overdue", due_date=today - timedelta(days=1), status=TaskStatus.AWAITING_REPORTS),
            Task(case=self.case, title="Later overdue", due_date=today - timedelta(days=1)),
        ]
        Task.objects.bulk_create(tasks)
        recorded_at = timezone.now()
        vitals = VitalEntry.objects.bulk_create([
            VitalEntry(case=self.case, recorded_at=recorded_at, pr=60 + index % 20) for index in range(100)
        ])
        expected_counts = {"total": 105, "open": 4, "today": 1, "upcoming": 1,
                           "overdue": 2, "awaiting": 1, "completed": 100}
        observed = []
        original = views._serialize_case_row

        def capture(row, **kwargs):
            observed.append((len(row.prefetched_mobile_tasks), len(row.prefetched_mobile_vitals)))
            return original(row, **kwargs)

        with patch("api.views._serialize_case_row", side_effect=capture):
            listing = self.client.get(reverse("api:case_list"), {"bucket": "all", "assigned_to": "all"})
            search = self.client.post(reverse("api:case_search"),
                                      {"query": "Synthetic", "bucket": "all", "assigned_to": "all"}, format="json")
            summary = views._mobile_case_payload(self.case, user=self.user)
        for response in (listing, search):
            self.assertEqual(response.status_code, 200, response.content)
        rows = [listing.json()["results"][0], search.json()["results"][0], summary]
        self.assertEqual(observed, [(1, 1)] * 3)
        for row in rows:
            self.assertEqual(row["task_counts"], expected_counts)
            self.assertEqual(row["next_task"]["id"], tasks[-2].pk)
            self.assertEqual(row["latest_vital"]["id"], vitals[-1].pk)

    def test_empty_and_repeated_case_summaries_do_not_reuse_stale_prefetch(self):
        self.task.delete()
        first = views._mobile_case_payload(self.case, user=self.user)
        self.assertEqual(first["task_counts"], dict.fromkeys(first["task_counts"], 0))
        self.assertIsNone(first["next_task"])
        self.assertIsNone(first["latest_vital"])
        task = Task.objects.create(case=self.case, title="New task", due_date=timezone.localdate())
        vital = VitalEntry.objects.create(case=self.case, pr=80)
        second = views._mobile_case_payload(self.case, user=self.user)
        self.assertEqual(second["task_counts"]["total"], 1)
        self.assertEqual(second["next_task"]["id"], task.pk)
        self.assertEqual(second["latest_vital"]["id"], vital.pk)

    def test_stale_notification_cleanup_is_bounded_and_backlog_stays_hidden(self):
        MobileNotification.objects.all().delete()
        stale = [MobileNotification.objects.create(user=self.user, notification_type=MobileNotificationType.RED_FLAG)
                 for _ in range(5)]
        self.assertEqual(purge_stale_notifications_for_user(self.user, limit=2), 2)
        self.assertEqual(MobileNotification.objects.filter(pk__in=[row.pk for row in stale]).count(), 3)
        self.assertFalse(authorized_notification_queryset(self.user).exists())
        self.assertEqual(purge_stale_notifications_for_user(self.user, limit=2), 2)
        self.assertEqual(purge_stale_notifications_for_user(self.user, limit=2), 1)

    def test_suspended_notifications_do_not_run_foreground_housekeeping(self):
        from .notifications import create_mobile_notification
        with suspend_mobile_notifications(), patch("api.notifications.purge_expired_mobile_notifications") as purge:
            self.assertIsNone(create_mobile_notification(user=self.user, notification_type=MobileNotificationType.RED_FLAG,
                                                         case=self.case))
        purge.assert_not_called()
