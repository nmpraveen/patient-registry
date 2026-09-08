"""Regressions for the combined Stage 2 review and retained-schema rollback."""
from datetime import timedelta
from copy import deepcopy
import hashlib
import io
import json
import zipfile
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    CallLog, CallOutcome, CaseActivityLog, DepartmentConfig, Task, TaskStatus,
    RCH_REMINDER_INTERVAL_DAYS, RCH_REMINDER_TASK_TITLE,
)
from .task_editing import task_values
from .test_task_calls import TaskCallFixture
from . import database_bundle


class TaskReviewFixTests(TaskCallFixture, TestCase):
    def cancel_task(self):
        self.task.status = TaskStatus.CANCELLED
        self.task.save()

    def setup_rch(self):
        self.case.category, _ = DepartmentConfig.objects.get_or_create(name="ANC")
        self.case.rch_bypass = True
        self.case.rch_number = ""
        self.case.save()
        self.task.title = RCH_REMINDER_TASK_TITLE
        self.task.save()

    def reminders(self):
        return Task.objects.filter(case=self.case, title=RCH_REMINDER_TASK_TITLE,
                                   status=TaskStatus.SCHEDULED).exclude(pk=self.task.pk)

    def test_cancelled_web_task_cannot_complete_or_revive_and_retains_draft(self):
        self.cancel_task()
        for status in (TaskStatus.COMPLETED, TaskStatus.SCHEDULED, TaskStatus.AWAITING_REPORTS):
            with self.subTest(status=status):
                response = self.client.post(self.edit_url, {**self.draft(), "status": status, "notes": "Unsaved draft"})
                self.assertEqual(response.status_code, 200)
                self.assertIn("status", response.context["form"].errors)
                self.assertContains(response, "Unsaved draft")
                self.task.refresh_from_db()
                self.assertEqual(self.task.status, TaskStatus.CANCELLED)
                self.assertEqual(self.task.notes, "Original note")
        self.assertFalse(CaseActivityLog.objects.filter(task=self.task).exists())

    def test_cancelled_api_task_cannot_complete_or_revive(self):
        self.cancel_task()
        for status in (TaskStatus.COMPLETED, TaskStatus.SCHEDULED, TaskStatus.AWAITING_REPORTS):
            with self.subTest(status=status):
                response = self.patch_task(self.task, status=status)
                self.assertEqual(response.status_code, 400)
                self.assertIn("status", response.data["errors"])
                self.task.refresh_from_db()
                self.assertEqual(self.task.status, TaskStatus.CANCELLED)
        self.assertFalse(CaseActivityLog.objects.filter(task=self.task).exists())

    def test_cancelled_task_notes_remain_editable_without_status_transition(self):
        self.cancel_task()
        response = self.client.post(self.edit_url, {**self.draft(), "notes": "Web correction"})
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        response = self.patch_task(self.task, notes="API correction")
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual((self.task.status, self.task.notes), (TaskStatus.CANCELLED, "API correction"))

    def test_api_rch_completion_creates_one_audited_followup_and_replay_is_stable(self):
        self.setup_rch()
        payload = {"status": TaskStatus.COMPLETED, "client_write_id": "rch-full-review",
                   "base_updated_at": self.task.updated_at.isoformat(), "base_values": task_values(self.task)}
        url = reverse("api:task_detail", args=[self.task.pk])
        response = self.api.patch(url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        reminder = self.reminders().get()
        self.assertEqual(reminder.due_date, timezone.localdate() + timedelta(days=RCH_REMINDER_INTERVAL_DAYS))
        self.assertEqual(CaseActivityLog.objects.filter(task=reminder).count(), 1)
        replay = self.api.patch(url, payload, format="json")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data, response.data)
        self.assertEqual(self.reminders().count(), 1)
        self.assertEqual(CaseActivityLog.objects.filter(task=reminder).count(), 1)

    def test_web_rch_completion_retains_same_followup_policy(self):
        self.setup_rch()
        response = self.client.post(self.edit_url, {**self.draft(), "status": TaskStatus.COMPLETED})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.reminders().count(), 1)

    def test_api_rch_followup_activity_failure_rolls_back_entire_completion(self):
        self.setup_rch()
        with patch("patients.views.create_case_activity", side_effect=RuntimeError("follow-up audit unavailable")):
            with self.assertRaisesMessage(RuntimeError, "follow-up audit unavailable"):
                self.patch_task(self.task, status=TaskStatus.COMPLETED)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SCHEDULED)
        self.assertFalse(self.reminders().exists())
        self.assertFalse(CaseActivityLog.objects.filter(case=self.case).exists())

    def test_legacy_insert_omitting_reason_works_with_retained_new_schema(self):
        # Match the columns supplied by pre-Stage-2 ORM code after a code-only rollback.
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO patients_calllog (case_id, outcome, notes, created_at, staff_user_id) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id, reason",
                [self.case.pk, CallOutcome.NO_ANSWER, "Legacy code", timezone.now(), self.user.pk],
            )
            call_id, reason = cursor.fetchone()
        self.assertEqual(reason, "")
        self.assertEqual(CallLog.objects.get(pk=call_id).reason, "")

    def test_reason_bundles_export_version_three_and_keep_reason(self):
        CallLog.objects.create(case=self.case, outcome=CallOutcome.NO_ANSWER, reason="Retain this reason")
        archive, manifest, _ = database_bundle.create_bundle_archive()
        self.assertEqual(manifest["schema_version"], 3)
        _, payload = database_bundle.load_bundle_archive(archive)
        self.assertEqual(payload["cases"][0]["call_logs"][0]["reason"], "Retain this reason")
        database_bundle._replace_patient_data(payload)
        self.assertEqual(CallLog.objects.get().reason, "Retain this reason")

    def test_predecessor_bundles_restore_without_reasons_and_keep_v2_reference_validation(self):
        CallLog.objects.create(case=self.case, outcome=CallOutcome.NO_ANSWER)
        archive, _, _ = database_bundle.create_bundle_archive()
        manifest, original = database_bundle.load_bundle_archive(archive)
        for version in (1, 2):
            with self.subTest(version=version):
                payload = deepcopy(original)
                del payload["cases"][0]["call_logs"][0]["reason"]
                data = database_bundle._json_bytes(payload)
                legacy_manifest = {**manifest, "schema_version": version,
                                   "patient_data_sha256": hashlib.sha256(data).hexdigest()}
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(database_bundle.PATIENT_DATA_FILENAME, data)
                    bundle.writestr(database_bundle.MANIFEST_FILENAME, json.dumps(legacy_manifest))
                _, loaded = database_bundle.load_bundle_archive(archive.getvalue())
                database_bundle._replace_patient_data(loaded)
                self.assertEqual(CallLog.objects.get().reason, "")
        broken = deepcopy(original)
        broken["patients"] = []
        data = database_bundle._json_bytes(broken)
        manifest.update(schema_version=2, counts=database_bundle.compute_payload_counts(broken),
                        patient_data_sha256=hashlib.sha256(data).hexdigest())
        with self.assertRaisesMessage(database_bundle.BundleValidationError, "references patient"):
            database_bundle._validate_manifest_and_payload(manifest, broken, data)
        manifest["schema_version"] = 4
        with self.assertRaisesMessage(database_bundle.BundleValidationError, "not supported"):
            database_bundle._validate_manifest_and_payload(manifest, broken, data)
