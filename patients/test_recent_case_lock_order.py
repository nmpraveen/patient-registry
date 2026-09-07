"""Recent Cases writes retain clinical state and serialize with patient edits."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from django.db import close_old_connections, connections
from django.forms.models import model_to_dict
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from . import test_follow_up
from .forms import PatientForm, RecentCaseUpdateForm
from .models import AuditEvent, Case, Patient


class RecentCaseAuditTests(TestCase):
    client_class = test_follow_up.FollowUpTests.client_class
    setUp = test_follow_up.FollowUpTests.setUp
    case = test_follow_up.FollowUpTests.case

    def test_recent_edit_audit_failure_rolls_back_fields_and_activity(self):
        case = self.case(diagnosis="Before", notes="Keep these notes")
        before = (case.diagnosis, case.notes, case.updated_at, case.patient_id, case.status, case.edd)
        activity_count = case.activity_logs.count()
        with patch("patients.audit.record_audit_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("patients:recent_case_update", args=[case.pk]),
                    {"diagnosis": "After", "notes": "New notes"})
        case.refresh_from_db()
        self.assertEqual((case.diagnosis, case.notes, case.updated_at, case.patient_id, case.status, case.edd), before)
        self.assertEqual(case.activity_logs.count(), activity_count)

    def test_recent_edit_rejects_changed_or_merged_patient_link_without_writing(self):
        case = self.case(diagnosis="Before", notes="Keep these notes")
        other = self.case().patient
        original_save = RecentCaseUpdateForm.save
        def relink_before_save(form, *args, **kwargs):
            Case.objects.filter(pk=case.pk).update(patient=other)
            return original_save(form, *args, **kwargs)
        with patch.object(RecentCaseUpdateForm, "save", relink_before_save):
            response = self.client.post(reverse("patients:recent_case_update", args=[case.pk]),
                {"diagnosis": "After", "notes": "New notes"})
        self.assertEqual(response.status_code, 400)
        case.refresh_from_db()
        self.assertEqual((case.diagnosis, case.notes, case.patient_id), ("Before", "Keep these notes", other.pk))
        target = self.case().patient
        def merge_before_save(form, *args, **kwargs):
            Patient.objects.filter(pk=other.pk).update(merged_into=target)
            return original_save(form, *args, **kwargs)
        with patch.object(RecentCaseUpdateForm, "save", merge_before_save):
            response = self.client.post(reverse("patients:recent_case_update", args=[case.pk]),
                {"diagnosis": "After", "notes": "New notes"})
        self.assertEqual(response.status_code, 400)
        case.refresh_from_db()
        self.assertEqual((case.diagnosis, case.notes), ("Before", "Keep these notes"))
        self.assertFalse(AuditEvent.objects.filter(case_id=case.pk, action="patients.case.recent_updated").exists())


class RecentCasePatientLockTests(TransactionTestCase):
    client_class = test_follow_up.FollowUpTests.client_class
    setUp = test_follow_up.FollowUpTests.setUp
    case = test_follow_up.FollowUpTests.case

    def test_actual_recent_and_patient_posts_finish_without_deadlock_or_lost_fields(self):
        case = self.case(prefix="MRS", age=25, gender="FEMALE", diagnosis="Before", notes="Before notes")
        clinical_before = (case.status, case.anc_outcome, case.edd, case.usg_edd, case.patient_id)
        original_updated_at = case.updated_at
        identity_client = self.client_class()
        identity_client.force_login(self.user)
        patient = Patient.objects.get(pk=case.patient_id)
        identity_data = {key: value if value is not None else ""
            for key, value in model_to_dict(patient, fields=PatientForm.Meta.fields).items()}
        identity_data["first_name"] = "Concurrent Identity"
        patient_locked, recent_case_locked = Event(), Event()

        def identity_hook(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if 'FROM "patients_patient"' in sql and "FOR UPDATE" in sql and not patient_locked.is_set():
                patient_locked.set()
                self.assertTrue(recent_case_locked.wait(5))
            return result

        def recent_hook(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if 'FROM "patients_case"' in sql and "FOR UPDATE" in sql:
                recent_case_locked.set()
            return result

        def post(client, route, data, hook, wait_for_patient=False):
            close_old_connections()
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                if wait_for_patient:
                    self.assertTrue(patient_locked.wait(5))
                with connections["default"].execute_wrapper(hook):
                    return client.post(route, data)
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            identity = pool.submit(post, identity_client,
                reverse("patients:patient_edit", args=[patient.pk]), identity_data, identity_hook)
            recent = pool.submit(post, self.client, reverse("patients:recent_case_update", args=[case.pk]),
                {"diagnosis": "Recent diagnosis", "notes": "Recent notes"}, recent_hook, True)
            identity_response, recent_response = identity.result(timeout=15), recent.result(timeout=15)
        self.assertEqual(identity_response.status_code, 302)
        self.assertEqual(recent_response.status_code, 200)
        case.refresh_from_db()
        patient.refresh_from_db()
        self.assertEqual((case.first_name, patient.first_name), ("Concurrent Identity", "Concurrent Identity"))
        self.assertEqual((case.diagnosis, case.notes), ("Recent diagnosis", "Recent notes"))
        self.assertEqual((case.status, case.anc_outcome, case.edd, case.usg_edd, case.patient_id), clinical_before)
        self.assertNotEqual(case.updated_at, original_updated_at)
        self.assertTrue(case.activity_logs.filter(note="Diagnosis updated: Before -> Recent diagnosis").exists())
        self.assertTrue(case.activity_logs.filter(note="Recent notes").exists())
        self.assertTrue(AuditEvent.objects.filter(case_id=case.pk, actor_user_id=self.user.pk,
            action="patients.case.recent_updated").exists())
