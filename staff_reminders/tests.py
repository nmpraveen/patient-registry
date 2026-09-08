from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone as dt_timezone
from io import StringIO
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from patients.models import AuditEvent, Case, RoleSetting
from patients.test_client import AuthVersionTestClient
from patients.auth_security import bump_auth_version, current_auth_version
from patients.task_editing import lock_edit_actor
from .models import Reminder, ReminderOccurrence
from .seed import seed_demo_reminders
from .services import (StaleReminder, complete_occurrence, create_reminder, hospital_today,
                       occurrence_date, schedule_reminders, update_reminder)


class CalendarTests(SimpleTestCase):
    def test_month_end_does_not_drift(self):
        self.assertEqual([occurrence_date(date(2025, 1, 31), "MONTHLY", i) for i in range(4)],
                         [date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31), date(2025, 4, 30)])

    def test_leap_anchor_returns_on_next_leap_year(self):
        self.assertEqual(occurrence_date(date(2024, 2, 29), "YEARLY", 1), date(2025, 2, 28))
        self.assertEqual(occurrence_date(date(2024, 2, 29), "YEARLY", 4), date(2028, 2, 29))

    def test_two_months_and_once_and_upper_bound(self):
        self.assertEqual(occurrence_date(date(2025, 12, 31), "EVERY_TWO_MONTHS", 1), date(2026, 2, 28))
        self.assertEqual(occurrence_date(date(2025, 12, 31), "EVERY_TWO_MONTHS", 2), date(2026, 4, 30))
        self.assertIsNone(occurrence_date(date(2025, 1, 1), "ONCE", 1))
        self.assertIsNone(occurrence_date(date(9999, 12, 31), "MONTHLY", 1))

    @override_settings(TIME_ZONE="Asia/Kolkata")
    def test_hospital_midnight_ignores_request_timezone(self):
        from django.utils import timezone
        with timezone.override("America/New_York"), patch("staff_reminders.services.timezone.now", return_value=datetime(2026, 9, 7, 18, 30, tzinfo=dt_timezone.utc)):
            self.assertEqual(hospital_today(), date(2026, 9, 8))


class ReminderFixture:
    def setUp(self):
        super().setUp()
        role, _ = RoleSetting.objects.get_or_create(role_name="Reminder test staff")
        group, _ = Group.objects.get_or_create(name=role.role_name)
        self.owner = get_user_model().objects.create_user(username="reminder-owner")
        self.assignee = get_user_model().objects.create_user(username="reminder-assignee")
        self.other = get_user_model().objects.create_user(username="reminder-other")
        self.manager = get_user_model().objects.create_user(username="reminder-manager", is_superuser=True)
        for user in (self.owner, self.assignee, self.other):
            user.groups.add(group)

    def create(self, **overrides):
        values = {"title": "Synthetic supplies check", "assignee_id": self.assignee.pk,
                  "due_date": date(2025, 1, 31), "advance_notice_days": 3, "recurrence": "MONTHLY"}
        values.update(overrides)
        return create_reminder(self.owner, values)


class ReminderServiceTests(ReminderFixture, TestCase):
    def test_bounded_catchup_resume_and_repeat(self):
        reminder = self.create()
        result = schedule_reminders(as_of=date(2025, 5, 31), limit=2, per_reminder=2)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["remaining_definitions"], 1)
        result = schedule_reminders(as_of=date(2025, 5, 31), limit=20)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["remaining_definitions"], 0)
        self.assertEqual(schedule_reminders(as_of=date(2025, 5, 31))["created"], 0)
        self.assertEqual(list(reminder.occurrences.values_list("due_date", flat=True)),
                         [date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31), date(2025, 4, 30), date(2025, 5, 31)])

    def test_advance_notice_inclusive_and_once_never_repeats(self):
        self.create()
        self.create(recurrence="ONCE")
        self.assertEqual(schedule_reminders(as_of=date(2025, 2, 24))["created"], 0)
        self.assertEqual(schedule_reminders(as_of=date(2025, 2, 25))["created"], 1)

    def test_completion_preserves_anchor_history_and_replay(self):
        reminder = self.create()
        occurrence = reminder.occurrences.get()
        first = complete_occurrence(self.assignee, occurrence.pk, 1)
        reminder = update_reminder(self.owner, reminder.pk, {"assignee_id": self.other.pk}, 1)
        replay = complete_occurrence(self.owner, occurrence.pk, 1)
        self.assertEqual(replay.completed_at, first.completed_at)
        self.assertEqual(replay.completed_by_id, self.assignee.pk)
        self.assertEqual(reminder.due_date, date(2025, 1, 31))
        self.assertEqual(AuditEvent.objects.filter(action="staff_reminder.completed", object_id=str(reminder.pk)).count(), 1)

    def test_completion_rejects_stale_definition(self):
        reminder = self.create()
        update_reminder(self.owner, reminder.pk, {"assignee_id": self.other.pk}, 1)
        with self.assertRaises(StaleReminder):
            complete_occurrence(self.owner, reminder.occurrences.get().pk, 1)
        self.assertIsNone(reminder.occurrences.get().completed_at)

    def test_deactivated_staff_pause_catchup_until_reassigned(self):
        reminder = self.create()
        self.assignee.is_active = False
        self.assignee.save(update_fields=["is_active"])
        self.assertEqual(schedule_reminders(as_of=date(2025, 3, 31))["created"], 0)
        update_reminder(self.owner, reminder.pk, {"assignee_id": self.other.pk}, 1)
        self.assertEqual(schedule_reminders(as_of=date(2025, 3, 31))["created"], 2)

    def test_last_staff_group_loss_pauses_cursor_and_restoration_resumes_anchor(self):
        reminder = self.create()
        completed = complete_occurrence(self.owner, reminder.occurrences.get().pk, 1)
        before = (reminder.next_index, reminder.next_notice_date, reminder.last_scheduled_at)
        group = self.assignee.groups.get()
        self.assignee.groups.clear()
        self.assertEqual(schedule_reminders(as_of=date(2025, 3, 31))["created"], 0)
        self.assertEqual(schedule_reminders(as_of=date(2025, 3, 31))["remaining_definitions"], 0)
        reminder.refresh_from_db()
        self.assertEqual((reminder.next_index, reminder.next_notice_date, reminder.last_scheduled_at), before)
        self.assertEqual(reminder.occurrences.count(), 1)
        completed.refresh_from_db()
        self.assertIsNotNone(completed.completed_at)
        self.assignee.groups.add(group)
        self.assertEqual(schedule_reminders(as_of=date(2025, 3, 31))["created"], 2)
        self.assertEqual(list(reminder.occurrences.values_list("due_date", flat=True)),
                         [date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31)])

    def test_deleted_role_pauses_but_active_superuser_needs_no_group(self):
        reminder = self.create()
        RoleSetting.objects.filter(role_name="Reminder test staff").delete()
        self.assertEqual(schedule_reminders(as_of=date(2025, 3, 31))["created"], 0)
        reminder.refresh_from_db()
        self.assertEqual(reminder.next_index, 1)
        update_reminder(self.manager, reminder.pk, {"assignee_id": self.manager.pk}, 1)
        self.assertEqual(schedule_reminders(as_of=date(2025, 3, 31))["created"], 2)

    def test_authorization_loss_after_selection_does_not_advance_cursor(self):
        reminder = self.create()

        def revoke_then_lock(actor):
            self.assignee.groups.clear()
            return lock_edit_actor(actor)

        with patch("staff_reminders.services.lock_edit_actor", side_effect=revoke_then_lock):
            self.assertEqual(schedule_reminders(as_of=date(2025, 3, 31))["created"], 0)
        reminder.refresh_from_db()
        self.assertEqual(reminder.next_index, 1)
        self.assertIsNone(reminder.last_scheduled_at)
        self.assertEqual(reminder.occurrences.count(), 1)

    def test_deactivation_preserves_rows_and_stops_completion(self):
        reminder = self.create()
        update_reminder(self.owner, reminder.pk, {"is_active": False}, 1)
        self.assertEqual(schedule_reminders(as_of=date(2026, 1, 1))["created"], 0)
        with self.assertRaises(ValidationError):
            complete_occurrence(self.owner, reminder.occurrences.get().pk, 2)
        self.assertEqual(reminder.occurrences.count(), 1)

    def test_notice_edit_preserves_completed_history(self):
        reminder = self.create()
        first = complete_occurrence(self.owner, reminder.occurrences.get().pk, 1)
        update_reminder(self.owner, reminder.pk, {"advance_notice_days": 10}, 1)
        first.refresh_from_db()
        self.assertEqual(first.notice_date, date(2025, 1, 28))
        self.assertEqual(schedule_reminders(as_of=date(2025, 2, 18))["created"], 1)

    def test_duplicate_occurrence_database_constraint(self):
        reminder = self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReminderOccurrence.objects.create(reminder=reminder, index=0, due_date=reminder.due_date, notice_date=reminder.due_date)

    def test_failed_audit_rolls_back_creation(self):
        with patch("staff_reminders.services.record_audit_event", side_effect=RuntimeError("synthetic audit failure")):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertEqual(Reminder.objects.count(), 0)
        self.assertEqual(ReminderOccurrence.objects.count(), 0)

    def test_scheduler_command_is_observable_and_bounded(self):
        self.create()
        output = StringIO()
        call_command("schedule_staff_reminders", as_of=date(2025, 5, 31), limit=1, stdout=output)
        self.assertIn('"created": 1', output.getvalue())
        self.assertIn('"remaining_definitions": 1', output.getvalue())

    def test_seed_is_gated_idempotent_and_nonclinical(self):
        with override_settings(ALLOW_MOCK_DATA_SEEDING=False), self.assertRaises(PermissionDenied):
            seed_demo_reminders(self.owner)
        before = Case.objects.count()
        with override_settings(ALLOW_MOCK_DATA_SEEDING=True):
            a = seed_demo_reminders(self.owner)
            b = seed_demo_reminders(self.owner)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(Case.objects.count(), before)


class ReminderAPITests(ReminderFixture, TestCase):
    client_class = AuthVersionTestClient
    prefix = "/api/staff/reminders/"

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.owner)
        self.reminder = self.create()

    def test_scope_denied_ids_and_assignee_reassignment(self):
        occurrence = self.reminder.occurrences.get()
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get(self.prefix).json()["count"], 0)
        self.assertEqual(self.api.get(f"{self.prefix}{self.reminder.pk}/").status_code, 404)
        self.assertEqual(self.api.get(f"{self.prefix}occurrences/?reminder_id={self.reminder.pk}").status_code, 404)
        self.assertEqual(self.api.post(f"{self.prefix}occurrences/{occurrence.pk}/complete/", {"version": 1}).status_code, 404)
        self.api.force_authenticate(self.assignee)
        self.assertEqual(self.api.get(self.prefix).json()["count"], 1)
        update_reminder(self.owner, self.reminder.pk, {"assignee_id": self.other.pk}, 1)
        self.assertEqual(self.api.get(self.prefix).json()["count"], 0)
        self.assertEqual(self.api.post(f"{self.prefix}occurrences/{occurrence.pk}/complete/", {"version": 1}).status_code, 404)

    def test_unconfigured_or_inactive_staff_denied(self):
        stranger = get_user_model().objects.create_user(username="unconfigured", is_staff=True)
        self.api.force_authenticate(stranger)
        self.assertEqual(self.api.get(self.prefix).status_code, 403)
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.get(self.prefix).status_code, 403)

    def test_schema_and_pagination_metadata_and_no_store(self):
        response = self.api.get(self.prefix)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"count", "next", "previous", "results", "server_now", "server_today"})
        self.assertTrue(response.json()["results"][0]["can_assign"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_invalid_body_is_400_not_server_error(self):
        self.assertEqual(self.api.post(self.prefix, [{"title": "invalid shape"}], format="json").status_code, 400)

    def test_revoked_jwt_between_authentication_and_write_is_denied(self):
        token = AccessToken.for_user(self.owner)
        token["auth_version"] = current_auth_version(self.owner)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        def revoke_then_lock(actor):
            bump_auth_version(actor, reason="synthetic race")
            return lock_edit_actor(actor)

        with patch("staff_reminders.services.lock_edit_actor", side_effect=revoke_then_lock):
            response = api.patch(f"{self.prefix}{self.reminder.pk}/", {"version": 1, "title": "Must not save"}, format="json")
        self.assertEqual(response.status_code, 401)
        self.reminder.refresh_from_db()
        self.assertEqual(self.reminder.title, "Synthetic supplies check")

    def test_create_validation_and_immutable_anchor(self):
        self.assertEqual(self.api.post(self.prefix, {"title": " ", "assignee_id": self.assignee.pk, "due_date": "2026-09-01"}).status_code, 400)
        url = f"{self.prefix}{self.reminder.pk}/"
        self.assertEqual(self.api.patch(url, {"version": 1, "due_date": "2026-10-01"}, format="json").status_code, 400)
        self.assertEqual(self.api.patch(url, {"title": "New"}, format="json").status_code, 400)
        self.assertEqual(self.api.patch(url, {"version": 1, "title": "New"}, format="json").status_code, 200)
        self.assertEqual(self.api.patch(url, {"version": 1, "title": "Stale"}, format="json").status_code, 409)

    def test_completion_version_and_idempotent_history(self):
        occurrence = self.reminder.occurrences.get()
        url = f"{self.prefix}occurrences/{occurrence.pk}/complete/"
        self.assertEqual(self.api.post(url, {}, format="json").status_code, 400)
        self.assertEqual(self.api.post(url, {"version": 9}, format="json").status_code, 409)
        first = self.api.post(url, {"version": 1}, format="json")
        second = self.api.post(url, {"version": 1}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["completed_at"], second.json()["completed_at"])
        self.assertEqual(self.api.get(f"{self.prefix}occurrences/?status=completed").json()["count"], 1)
        self.assertFalse(first.json()["can_complete"])

    def test_manager_and_assignee_options(self):
        self.api.force_authenticate(self.manager)
        self.assertEqual(self.api.get(self.prefix).json()["count"], 1)
        self.assignee.is_active = False
        self.assignee.save(update_fields=["is_active"])
        options = self.api.get(f"{self.prefix}assignees/").json()["results"]
        self.assertNotIn(self.assignee.pk, [row["id"] for row in options])
        self.assertEqual(self.api.patch(f"{self.prefix}{self.reminder.pk}/", {"version": 1, "assignee_id": self.assignee.pk}, format="json").status_code, 400)

    def test_web_forms_history_scope_and_csrf(self):
        self.client.force_login(self.owner)
        for url in ("/staff/reminders/", "/staff/reminders/new/", f"/staff/reminders/{self.reminder.pk}/", f"/staff/reminders/{self.reminder.pk}/edit/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/staff/reminders/{self.reminder.pk}/edit/").status_code, 404)
        csrf_client = AuthVersionTestClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(csrf_client.post(f"/staff/reminders/occurrences/{self.reminder.occurrences.get().pk}/complete/", {"version": 1}).status_code, 403)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locking required")
class ReminderConcurrencyTests(ReminderFixture, TransactionTestCase):
    def parallel(self, function):
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(run) for _ in range(2)]
            return [result.result(timeout=30) for result in results]

    def test_two_real_schedulers_dedupe_and_resume(self):
        reminder = self.create()
        self.parallel(lambda: schedule_reminders(as_of=date(2025, 12, 31), per_reminder=120))
        self.assertEqual(reminder.occurrences.count(), 12)
        self.assertEqual(schedule_reminders(as_of=date(2025, 12, 31))["created"], 0)

    def test_concurrent_completions_have_one_receipt(self):
        reminder = self.create()
        occurrence = reminder.occurrences.get()
        results = self.parallel(lambda: complete_occurrence(self.owner, occurrence.pk, 1).completed_at)
        self.assertEqual(results[0], results[1])
        self.assertEqual(AuditEvent.objects.filter(action="staff_reminder.completed", object_id=str(reminder.pk)).count(), 1)

    def test_concurrent_edits_reject_one_stale_writer(self):
        reminder = self.create()

        def edit():
            try:
                update_reminder(self.owner, reminder.pk, {"title": "Changed"}, 1)
                return "saved"
            except StaleReminder:
                return "stale"

        self.assertCountEqual(self.parallel(edit), ["saved", "stale"])
