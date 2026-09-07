"""Regression acceptance for the four consolidated Stage 1 review findings."""
import hashlib
import io
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from api.views import _case_edit_payload
from .database_bundle import create_bundle_archive, import_bundle_bytes
from .forms import CaseForm, RecentCaseUpdateForm
from .models import Case, CaseDataScope, CaseStatus, RoleSetting, TaskStatus, ensure_rch_reminder_task
from .test_follow_up import FollowUpTests


class AncReviewFixTests(TestCase):
    client_class = FollowUpTests.client_class
    setUp = FollowUpTests.setUp
    case = FollowUpTests.case
    task = FollowUpTests.task
    action = FollowUpTests.action
    ids = FollowUpTests.ids

    def scoped_editor(self):
        user = get_user_model().objects.create_user("scoped-review")
        group = Group.objects.create(name="ScopedReview")
        RoleSetting.objects.create(role_name=group.name, case_data_scope=CaseDataScope.ASSIGNED, can_case_edit=True)
        user.groups.add(group)
        self.api.force_authenticate(user)
        self.client.force_login(user)
        return user

    def test_allowed_assigned_web_get_post_and_api_replay_on_postgresql(self):
        user = self.scoped_editor()
        case = self.case(created_by=user)
        url = reverse("patients:anc_action", args=[case.pk])
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any('"patients_case"' in q["sql"] and "FOR UPDATE" in q["sql"] for q in queries))
        response = self.client.post(url, {"action": "correct_edd", "usg_edd": (self.today + timedelta(days=5)).isoformat(),
            "reason": "Synthetic correction", "base_updated_at": case.updated_at.isoformat(), "task_policy": "retain"})
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(self.action(case).status_code, 200)
        self.assertEqual(self.action(case).status_code, 200)
        self.assertEqual(case.activity_logs.filter(note__startswith="ANC outcome:").count(), 1)
        hidden = self.case()
        self.assertEqual(self.action(hidden).status_code, 404)
        self.assertEqual(self.client.get(reverse("patients:anc_action", args=[hidden.pk])).status_code, 404)

    def interleave_clinical_action(self, case, action):
        if action == "outcome":
            response = self.action(Case.objects.get(pk=case.pk))
        else:
            response = self.action(Case.objects.get(pk=case.pk), action="correct_edd",
                usg_edd=(self.today + timedelta(days=12)).isoformat())
        self.assertEqual(response.status_code, 200, response.data)

    def assert_clinical_action_preserved(self, case, action):
        case.refresh_from_db()
        if action == "outcome":
            self.assertEqual(case.anc_outcome, "delivery")
            self.assertEqual(case.status, CaseStatus.COMPLETED)
            self.assertEqual(case.activity_logs.filter(note__startswith="ANC outcome:").count(), 1)
        else:
            self.assertEqual(case.usg_edd, self.today + timedelta(days=12))
            self.assertEqual(case.activity_logs.filter(note__startswith="USG EDD corrected:").count(), 1)

    def test_recent_edits_preserve_interleaved_outcome_and_edd(self):
        for action in ("outcome", "correct_edd"):
            with self.subTest(action=action):
                case = self.case()
                original = RecentCaseUpdateForm.save
                def save(form, *args, **kwargs):
                    self.interleave_clinical_action(case, action)
                    return original(form, *args, **kwargs)
                with patch.object(RecentCaseUpdateForm, "save", save):
                    response = self.client.post(reverse("patients:recent_case_update", args=[case.pk]),
                        {"diagnosis": "Updated diagnosis", "notes": "Unrelated notes"})
                self.assertEqual(response.status_code, 200)
                self.assert_clinical_action_preserved(case, action)
                self.assertEqual(case.notes, "Unrelated notes")

    def test_full_web_edits_reject_interleaved_outcome_and_edd(self):
        for action in ("outcome", "correct_edd"):
            with self.subTest(action=action):
                case = self.case(prefix="MRS", age=25, gender="FEMALE")
                data = {key: value if value is not None else "" for key, value in _case_edit_payload(case).items()}
                data["notes"] = "Stale notes"
                data["rendered_baseline"] = self.client.get(reverse("patients:case_edit", args=[case.pk])).context["form"]["rendered_baseline"].value()
                original = CaseForm.save
                def save(form, *args, **kwargs):
                    self.interleave_clinical_action(case, action)
                    return original(form, *args, **kwargs)
                with patch.object(CaseForm, "save", save):
                    response = self.client.post(reverse("patients:case_edit", args=[case.pk]), data)
                self.assertContains(response, "This case changed while you were editing.")
                self.assert_clinical_action_preserved(case, action)
                self.assertNotEqual(case.notes, "Stale notes")

    def test_routine_edits_never_recreate_cancelled_resolved_reminders(self):
        for continuing in ("continue", "close"):
            for route in ("web", "api"):
                with self.subTest(continuing=continuing, route=route):
                    case = self.case(prefix="MRS", age=25, gender="FEMALE")
                    reminder = ensure_rch_reminder_task(case, self.user)
                    unrelated = self.task(case)
                    self.assertEqual(self.action(case, continue_follow_up=continuing,
                        task_policy="cancel_selected", cancel_task_ids=[reminder.pk]).status_code, 200)
                    case.refresh_from_db()
                    if route == "api":
                        response = self.api.patch(reverse("api:case_detail", args=[case.pk]), {
                            "notes": "Routine edit", "base_values": {"notes": case.notes},
                            "base_updated_at": case.updated_at.isoformat(), "client_write_id": f"routine-{case.pk}"}, format="json")
                        self.assertEqual(response.status_code, 200, response.data)
                    else:
                        data = {key: value if value is not None else "" for key, value in _case_edit_payload(case).items()}
                        data["notes"] = "Routine edit"
                        data["rendered_baseline"] = self.client.get(reverse("patients:case_edit", args=[case.pk])).context["form"]["rendered_baseline"].value()
                        response = self.client.post(reverse("patients:case_edit", args=[case.pk]), data)
                        self.assertEqual(response.status_code, 302)
                    reminder.refresh_from_db(); unrelated.refresh_from_db()
                    self.assertEqual(reminder.status, TaskStatus.CANCELLED)
                    self.assertEqual(case.tasks.count(), 2)
                    self.assertEqual(unrelated.status, TaskStatus.SCHEDULED)

    def test_retained_continuing_reminder_is_not_cancelled_or_duplicated(self):
        case = self.case()
        reminder = ensure_rch_reminder_task(case, self.user)
        self.assertEqual(self.action(case, continue_follow_up="continue").status_code, 200)
        case.refresh_from_db()
        self.assertIsNone(ensure_rch_reminder_task(case, self.user))
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, TaskStatus.SCHEDULED)
        self.assertEqual(case.tasks.count(), 1)
        closed = self.case(status=CaseStatus.COMPLETED)
        self.assertIsNone(ensure_rch_reminder_task(closed, self.user))

    def modified_bundle(self, changes, *, legacy=False):
        archive, _, _ = create_bundle_archive()
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            files = {name: bundle.read(name) for name in bundle.namelist()}
        payload = json.loads(files["patient_data.json"])
        if legacy:
            for record in payload["cases"]:
                for key in list(record):
                    if key.startswith("anc_outcome") or key in ("anc_referral_destination", "anc_continue_follow_up"):
                        del record[key]
        else:
            payload["cases"][0].update(changes)
        files["patient_data.json"] = json.dumps(payload).encode()
        manifest = json.loads(files["manifest.json"])
        for key, value in manifest.items():
            if isinstance(value, str) and len(value) == 64:
                manifest[key] = hashlib.sha256(files["patient_data.json"]).hexdigest()
        files["manifest.json"] = json.dumps(manifest).encode()
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w") as bundle:
            for name, data in files.items():
                bundle.writestr(name, data)
        return result.getvalue()

    def test_invalid_outcome_imports_fail_transactionally_legacy_import_remains_valid(self):
        case = self.case()
        valid = dict(anc_outcome="delivery", anc_outcome_date=self.today.isoformat(), anc_outcome_reason="Verified",
            anc_continue_follow_up=False)
        variants = ({"anc_outcome_date": None}, {"anc_outcome_reason": "  "},
            {"anc_outcome": "referral", "anc_referral_destination": " "},
            {"anc_continue_follow_up": None}, {"anc_continue_follow_up": "false"},
            {"anc_outcome_date": (self.today + timedelta(days=1)).isoformat()})
        with TemporaryDirectory() as directory, patch("patients.database_bundle.default_backup_dir", return_value=Path(directory)):
            for changes in variants:
                with self.subTest(changes=changes):
                    archive = self.modified_bundle(valid | changes)
                    with self.assertRaises(ValidationError):
                        import_bundle_bytes(archive)
                    case.refresh_from_db()
                    self.assertEqual(case.anc_outcome, "")
                    self.assertTrue(case.follow_up["edd_overdue"])
            import_bundle_bytes(self.modified_bundle({}, legacy=True))
        self.assertTrue(Case.objects.get(uhid=case.uhid).follow_up["edd_overdue"])

    def test_model_validation_enforces_same_outcome_invariants(self):
        case = self.case()
        case.anc_outcome = "referral"
        with self.assertRaises(ValidationError) as caught:
            case.full_clean()
        self.assertTrue({"anc_outcome_date", "anc_outcome_reason", "anc_referral_destination"}.issubset(caught.exception.message_dict))
