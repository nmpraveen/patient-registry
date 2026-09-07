"""Targeted regressions for ANC acknowledgement, validation, seed and lock feedback."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from . import test_follow_up, test_anc_review_fixes
from .anc import AncActionForm, apply_anc_action
from .database_bundle import create_bundle_archive, import_bundle_bytes
from .models import AuditEvent, Case, CaseStatus, Patient


class AncFinalFeedbackTests(TestCase):
    client_class = test_follow_up.FollowUpTests.client_class
    setUp = test_follow_up.FollowUpTests.setUp
    case = test_follow_up.FollowUpTests.case
    action = test_follow_up.FollowUpTests.action
    modified_bundle = test_anc_review_fixes.AncReviewFixTests.modified_bundle

    def test_loss_to_follow_up_cannot_continue_in_web_api_model_or_import(self):
        case = self.case()
        values = dict(outcome="loss_to_follow_up", continue_follow_up="continue")
        response = self.action(case, **values)
        self.assertEqual(response.status_code, 400)
        self.assertIn("continue_follow_up", response.data["errors"])
        response = self.client.post(reverse("patients:anc_action", args=[case.pk]), dict(
            action="outcome", base_updated_at=case.updated_at.isoformat(), reason="Verified",
            outcome_date=self.today.isoformat(), task_policy="retain", **values))
        self.assertContains(response, "Loss to follow-up must close the case.")
        case.refresh_from_db()
        self.assertEqual(case.anc_outcome, "")
        self.assertTrue(case.follow_up["edd_overdue"])
        case.anc_outcome = "loss_to_follow_up"
        case.anc_outcome_date = self.today
        case.anc_outcome_reason = "Verified"
        case.anc_continue_follow_up = True
        with self.assertRaises(ValidationError):
            case.full_clean()
        with TemporaryDirectory() as directory, patch("patients.database_bundle.default_backup_dir", return_value=Path(directory)):
            with self.assertRaises(ValidationError):
                import_bundle_bytes(self.modified_bundle(dict(anc_outcome="loss_to_follow_up",
                    anc_outcome_date=self.today.isoformat(), anc_outcome_reason="Verified", anc_continue_follow_up=True)))
        case.refresh_from_db()
        self.assertEqual(case.anc_outcome, "")
        self.assertEqual(self.action(case, outcome="loss_to_follow_up", continue_follow_up="close",
            client_write_id="valid-loss-close").status_code, 200)
        case.refresh_from_db()
        self.assertEqual(case.status, CaseStatus.LOSS_TO_FOLLOW_UP)

    @override_settings(ALLOW_MOCK_DATA_SEEDING=True)
    def test_follow_up_seed_exports_and_imports_as_valid_cases(self):
        call_command("seed_mock_data", count=12, follow_up_scenarios=True, stdout=io.StringIO())
        follow_up_cases = Case.objects.filter(metadata__seed_case_key__regex=r"^(edd_overdue|dormant|edd_missing|anc_resolved):")
        self.assertEqual(follow_up_cases.count(), 4)
        before = {}
        for case in follow_up_cases:
            missing = case.metadata["seed_case_key"].startswith("edd_missing:")
            if missing:
                self.assertEqual(case.metadata["entry_mode"], "quick_entry")
                case._skip_workflow_validation = True
                self.assertTrue(case.follow_up["edd_missing"])
            else:
                self.assertIsNotNone(case.lmp)
            case.full_clean()
            before[case.uhid] = (case.edd, case.lmp, case.anc_outcome)
        archive, _, _ = create_bundle_archive()
        with TemporaryDirectory() as directory, patch("patients.database_bundle.default_backup_dir", return_value=Path(directory)):
            import_bundle_bytes(archive)
        for case in Case.objects.filter(uhid__in=before):
            self.assertEqual((case.edd, case.lmp, case.anc_outcome), before[case.uhid])

    def test_mandatory_audit_failure_rolls_back_precise_anc_update(self):
        case = self.case()
        with patch("patients.audit.record_audit_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.action(case)
        case.refresh_from_db()
        self.assertEqual(case.anc_outcome, "")
        self.assertEqual(case.status, CaseStatus.ACTIVE)


class AncIdentityLockTests(TransactionTestCase):
    client_class = test_follow_up.FollowUpTests.client_class
    setUp = test_follow_up.FollowUpTests.setUp
    case = test_follow_up.FollowUpTests.case

    def test_anc_and_patient_identity_updates_complete_without_lock_inversion(self):
        for action in ("outcome", "correct_edd"):
            with self.subTest(action=action):
                case = self.case()
                patient_locked, case_locked = Event(), Event()
                def identity_write():
                    close_old_connections()
                    try:
                        with transaction.atomic():
                            with connections["default"].cursor() as cursor:
                                cursor.execute("SET LOCAL lock_timeout = '5s'")
                            patient = Patient.objects.select_for_update().get(pk=case.patient_id)
                            patient_locked.set()
                            self.assertTrue(case_locked.wait(5))
                            patient.first_name = "Updated"
                            patient.save()
                    finally:
                        connections["default"].close()
                def anc_write():
                    close_old_connections()
                    try:
                        with transaction.atomic():
                            with connections["default"].cursor() as cursor:
                                cursor.execute("SET LOCAL lock_timeout = '5s'")
                            locked = Case.objects.select_for_update().select_related("category").get(pk=case.pk)
                            case_locked.set()
                            self.assertTrue(patient_locked.wait(5))
                            form = AncActionForm(case=locked, data=dict(action=action,
                                base_updated_at=locked.updated_at, reason="Verified", outcome="delivery",
                                outcome_date=self.today, continue_follow_up="close", task_policy="retain",
                                usg_edd=self.today + timedelta(days=12)))
                            self.assertTrue(form.is_valid(), form.errors)
                            apply_anc_action(case=locked, user=self.user, data=form.cleaned_data)
                    finally:
                        connections["default"].close()
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(identity_write), pool.submit(anc_write)]
                    for future in futures:
                        future.result(timeout=15)
                case.refresh_from_db()
                self.assertEqual(case.first_name, "Updated")
                self.assertTrue(AuditEvent.objects.filter(case_id=case.pk, action="patients.case.anc_action").exists())
                if action == "outcome":
                    self.assertEqual((case.status, case.anc_outcome), (CaseStatus.COMPLETED, "delivery"))
                else:
                    self.assertEqual(case.usg_edd, self.today + timedelta(days=12))
