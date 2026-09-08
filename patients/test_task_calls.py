"""Stage 2 contracts exercised through real web/API write boundaries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from . import database_bundle
from .models import CallLog, CallOutcome, Case, CaseActivityLog, CaseDataScope, DepartmentConfig, RoleSetting, Task, TaskStatus
from .task_editing import task_values
from .test_client import AuthVersionTestClient


class TaskCallFixture:
    client_class = AuthVersionTestClient

    def setUp(self):
        self.user = get_user_model().objects.create_superuser("stage2", "stage2@example.invalid", "pass")
        category, _ = DepartmentConfig.objects.get_or_create(name="Medicine")
        self.case = Case.objects.create(uhid="STAGE2-SYNTHETIC", first_name="Synthetic", last_name="Patient",
                                       phone_number="9000000000", category=category, created_by=self.user, review_date=timezone.localdate())
        self.task = Task.objects.create(case=self.case, title="Review", due_date=timezone.localdate(),
                                       notes="Original note", frequency_label="Monthly", assigned_user=self.user, created_by=self.user)
        self.client.force_login(self.user)
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.edit_url = reverse("patients:task_edit", args=[self.task.pk])
        self.call_url = reverse("api:case_call_outcome", args=[self.case.pk])

    def draft(self):
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        return {**task_values(self.task), "edit_baseline": response.context["edit_baseline"]}

    def patch_task(self, before, **changes):
        return self.api.patch(reverse("api:task_detail", args=[self.task.pk]), {
            "base_updated_at": before.updated_at.isoformat(), "base_values": task_values(before),
            "client_write_id": "edit-" + str(timezone.now().timestamp()), **changes}, format="json")


class TaskCallContractTests(TaskCallFixture, TestCase):
    def test_visible_editor_persists_all_fields_and_audits_changes(self):
        draft = self.draft()
        draft.update(title="Medication review", due_date=(timezone.localdate() + timedelta(days=2)).isoformat(),
                     assigned_user="", task_type="CALL", frequency_label="Weekly", notes="New instructions")
        response = self.client.post(self.edit_url, draft)
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Medication review")
        self.assertEqual(self.task.frequency_label, "Weekly")
        self.assertEqual(self.task.notes, "New instructions")
        self.assertIsNone(self.task.assigned_user_id)
        log = CaseActivityLog.objects.filter(task=self.task, event_type="TASK").latest("id")
        self.assertIn("Monthly", log.note)
        self.assertIn("Weekly", log.note)
        self.assertEqual(log.user_id, self.user.pk)
        self.assertContains(self.client.get(reverse("patients:case_detail", args=[self.case.pk])), self.edit_url)

    def test_original_get_baseline_rejects_stale_overlap_and_retains_draft(self):
        first, second = self.draft(), self.draft()
        self.assertEqual(self.client.post(self.edit_url, {**first, "notes": "Winner"}).status_code, 302)
        response = self.client.post(self.edit_url, {**second, "notes": "My unsaved draft"})
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "My unsaved draft", status_code=409)
        self.task.refresh_from_db()
        self.assertEqual(self.task.notes, "Winner")
        self.assertEqual(CaseActivityLog.objects.filter(task=self.task).count(), 1)

    def test_web_api_interleaving_preserves_distinct_fields(self):
        draft = self.draft()
        self.assertEqual(self.patch_task(self.task, frequency_label="Weekly").status_code, 200)
        self.assertEqual(self.client.post(self.edit_url, {**draft, "notes": "Independent"}).status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual((self.task.notes, self.task.frequency_label), ("Independent", "Weekly"))

    def test_missing_tampered_other_task_or_editor_baseline_rejected(self):
        draft = self.draft()
        other = Task.objects.create(case=self.case, title="Other", due_date=timezone.localdate())
        other_token = self.client.get(reverse("patients:task_edit", args=[other.pk])).context["edit_baseline"]
        for token in ("", draft["edit_baseline"] + "tamper", other_token):
            with self.subTest(token=token[-10:]):
                self.assertEqual(self.client.post(self.edit_url, {**draft, "edit_baseline": token}).status_code, 409)
        second_user = get_user_model().objects.create_superuser("other", "other@example.invalid", "pass")
        self.client.force_login(second_user)
        self.assertEqual(self.client.post(self.edit_url, draft).status_code, 409)

    def test_web_quick_note_conflicts_with_full_edit(self):
        draft = self.draft()
        self.assertEqual(self.client.post(self.edit_url, {**draft, "notes": "First"}).status_code, 302)
        response = self.client.post(reverse("patients:task_quick_note", args=[self.task.pk]),
            {"edit_baseline": draft["edit_baseline"], "note": "Stale"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 409)
        self.task.refresh_from_db()
        self.assertEqual(self.task.notes, "First")

    def test_task_update_and_activity_roll_back_together(self):
        draft = self.draft()
        with patch("patients.views.create_case_activity", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.edit_url, {**draft, "notes": "Must roll back"})
        self.task.refresh_from_db()
        self.assertEqual(self.task.notes, "Original note")

    def test_notes_and_frequency_patch_clear_and_null_rules(self):
        response = self.patch_task(self.task, notes="", frequency_label="")
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual((self.task.notes, self.task.frequency_label), ("", ""))
        self.assertEqual(self.patch_task(self.task, notes=None).status_code, 400)
        self.assertEqual(self.patch_task(self.task, frequency_label="x" * 41).status_code, 400)

    def test_completion_preconditions_conflict_but_legacy_payload_replays(self):
        url = reverse("api:task_complete", args=[self.task.pk])
        baseline = {"status": self.task.status, "due_date": self.task.due_date.isoformat()}
        self.task.due_date += timedelta(days=1)
        self.task.save()
        self.assertEqual(self.api.post(url, {"client_write_id": "stale", "base_values": baseline}, format="json").status_code, 409)
        request = {"client_write_id": "legacy-complete"}
        for _ in range(2):
            self.assertEqual(self.api.post(url, request, format="json").status_code, 200)
        self.assertEqual(CaseActivityLog.objects.filter(task=self.task, event_type="TASK").count(), 1)

    def test_new_completion_preconditions_ignore_unrelated_notes_and_replay(self):
        url = reverse("api:task_complete", args=[self.task.pk])
        data = {"client_write_id": "current-complete", "base_values": {
            "status": self.task.status, "due_date": self.task.due_date.isoformat()}}
        self.task.notes = "Updated independently"
        self.task.save()
        for _ in range(2):
            self.assertEqual(self.api.post(url, data, format="json").status_code, 200)
        self.assertEqual(CaseActivityLog.objects.filter(task=self.task, event_type="TASK").count(), 1)
        self.assertEqual(self.api.post(url, {"base_values": {"status": "SCHEDULED"}}, format="json").status_code, 400)

    def test_taskless_reason_legacy_current_and_task_associated_matrix(self):
        for reason in ("", "   ", None, "x" * 501):
            self.assertEqual(self.api.post(self.call_url, {"outcome": "reached", "reason": reason}, format="json").status_code, 400)
        self.assertEqual(self.api.post(self.call_url, {"outcome": "reached"}, format="json").status_code, 201)
        self.assertEqual(CallLog.objects.get().reason, "")
        data = {"outcome": "reached", "task_id": self.task.pk, "reason": ""}
        self.assertEqual(self.api.post(self.call_url, data, format="json").status_code, 201)
        response = self.api.post(self.call_url, {"outcome": "reached", "reason": "  Appointment clarification  "}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["call_log"]["reason"], "Appointment clarification")
        self.assertIsNone(response.json()["call_log"]["task_id"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SCHEDULED)
        self.assertEqual(Task.objects.count(), 1)

    def test_lost_call_response_replay_keeps_one_call_and_one_visible_event(self):
        for payload in ({"outcome": "reached", "client_write_id": "legacy-call"},
                        {"outcome": "reached", "reason": "Check appointment", "client_write_id": "current-call"}):
            for _ in range(2):
                self.assertEqual(self.api.post(self.call_url, payload, format="json").status_code, 201)
        self.assertEqual(CallLog.objects.count(), 2)
        self.assertEqual(CaseActivityLog.objects.filter(event_type="CALL").count(), 2)
        page = self.client.get(reverse("patients:case_detail", args=[self.case.pk]), {"show_logs": "1"})
        self.assertEqual(len([e for e in page.context["timeline_entries"] if e["event_type"] == "CALL"]), 2)
        self.assertContains(page, "Check appointment")
        conflict = self.api.post(self.call_url, {"outcome": "reached", "reason": "Changed", "client_write_id": "current-call"}, format="json")
        self.assertEqual(conflict.status_code, 409)

    def test_general_web_call_and_cross_case_ids(self):
        url = reverse("patients:case_call_create", args=[self.case.pk])
        response = self.client.post(url, {"task": "", "reason": "Medicine clarification", "outcome": CallOutcome.NO_ANSWER}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["call_log"]["reason"], "Medicine clarification")
        foreign_case = Case.objects.create(uhid="OTHER-SYNTHETIC", first_name="Other", category=self.case.category)
        foreign_task = Task.objects.create(case=foreign_case, title="Other", due_date=timezone.localdate())
        self.assertEqual(self.api.post(self.call_url, {"outcome": "reached", "task_id": foreign_task.pk}, format="json").status_code, 404)
        self.assertEqual(self.client.post(url, {"task": foreign_task.pk, "reason": "Wrong case", "outcome": CallOutcome.NO_ANSWER}, HTTP_ACCEPT="application/json").status_code, 400)

    def test_new_reason_export_and_old_import_field_default(self):
        CallLog.objects.create(case=self.case, reason="Bundle reason", notes="Optional note", outcome=CallOutcome.NO_ANSWER)
        payload = database_bundle.build_patient_data_payload()
        call = payload["cases"][0]["call_logs"][0]
        self.assertEqual(call["reason"], "Bundle reason")
        # Exercise the real reconstruction without writing an on-disk backup.
        database_bundle._replace_patient_data(payload)
        self.assertEqual(CallLog.objects.get().reason, "Bundle reason")
        del call["reason"]
        database_bundle._replace_patient_data(payload)
        self.assertEqual(CallLog.objects.get().reason, "")

    def test_call_history_is_bounded_ordered_and_current_scope_applies(self):
        for number in range(22):
            CallLog.objects.create(case=self.case, reason=f"Synthetic call {number}", outcome=CallOutcome.NO_ANSWER)
        detail = self.api.get(reverse("api:case_detail", args=[self.case.pk])).json()
        calls = detail["call_logs"]
        self.assertEqual(len(calls), 20)
        self.assertEqual(calls[0]["reason"], "Synthetic call 21")
        self.assertEqual(calls[-1]["reason"], "Synthetic call 2")
        restricted = get_user_model().objects.create_user("restricted", password="pass")
        role = RoleSetting.objects.create(role_name="Stage2 restricted", case_data_scope=CaseDataScope.ASSIGNED,
                                          can_note_add=True, can_task_edit=True)
        group = Group.objects.create(name=role.role_name)
        restricted.groups.add(group)
        self.api.force_authenticate(restricted)
        self.assertEqual(self.api.get(reverse("api:case_detail", args=[self.case.pk])).status_code, 404)
        self.assertEqual(self.api.post(self.call_url, {"outcome": "reached", "reason": "Forbidden"}, format="json").status_code, 404)
        self.task.assigned_user = restricted
        self.task.save()
        self.assertEqual(self.api.get(reverse("api:case_detail", args=[self.case.pk])).status_code, 200)
        role.can_task_edit = False
        role.save()
        # force_authenticate deliberately retains the old Python user object;
        # the mutation must re-evaluate locked current role policy.
        response = self.api.patch(reverse("api:task_detail", args=[self.task.pk]), {
            "base_updated_at": self.task.updated_at.isoformat(), "base_values": task_values(self.task),
            "notes": "Forbidden edit", "client_write_id": "role-changed"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.notes, "Original note")


class TaskWriteConcurrencyTests(TaskCallFixture, TransactionTestCase):
    def test_two_web_editors_cannot_both_overwrite_the_same_field(self):
        if connection.vendor != "postgresql":
            self.skipTest("Requires PostgreSQL row locks")
        draft = self.draft()
        barrier = Barrier(2)
        def save(note):
            close_old_connections()
            try:
                client = AuthVersionTestClient()
                client.force_login(get_user_model().objects.get(pk=self.user.pk))
                barrier.wait(timeout=10)
                return client.post(self.edit_url, {**draft, "notes": note}).status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(save, ("Editor one", "Editor two")))
        self.assertEqual(sorted(results), [302, 409])
        self.assertEqual(CaseActivityLog.objects.filter(task=self.task, event_type="TASK").count(), 1)
