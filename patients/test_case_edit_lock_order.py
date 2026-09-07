"""Full web edits serialize with patient identity writes without losing drafts."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from django.db import close_old_connections, connections
from django.forms.models import model_to_dict
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from . import test_case_rendered_baseline as fixtures
from .forms import PatientForm
from .models import AuditEvent, Patient


class WebIdentityDraftTests(TestCase):
    client_class = fixtures.RenderedCaseBaselineTests.client_class
    setUp = fixtures.RenderedCaseBaselineTests.setUp
    case = fixtures.RenderedCaseBaselineTests.case
    edit_page = fixtures.RenderedCaseBaselineTests.edit_page

    def test_completed_patient_edit_rejects_old_draft_and_retains_original_token(self):
        case = self.case(prefix="MRS", age=25, gender="FEMALE")
        url, data = self.edit_page(case)
        data["notes"] = "Retain this browser draft"
        original_version = case.updated_at
        patient = case.patient
        patient.first_name = "Identity Updated"
        patient.save()
        case.refresh_from_db()
        self.assertNotEqual(case.updated_at, original_version)
        for _ in range(2):
            response = self.client.post(url, data)
            self.assertContains(response, "This case changed while you were editing.")
            self.assertEqual(response.context["form"]["notes"].value(), data["notes"])
            self.assertEqual(response.context["form"]["rendered_baseline"].value(), data["rendered_baseline"])
        case.refresh_from_db()
        patient.refresh_from_db()
        self.assertEqual((case.first_name, patient.first_name), ("Identity Updated", "Identity Updated"))
        self.assertNotEqual(case.notes, data["notes"])

    def test_current_web_identity_edit_preserves_mirrors_and_mandatory_audit(self):
        case = self.case(prefix="MRS", age=25, gender="FEMALE")
        url, data = self.edit_page(case)
        data.update(first_name="Web Identity", notes="Current draft")
        self.assertEqual(self.client.post(url, data).status_code, 302)
        case.refresh_from_db()
        self.assertEqual((case.first_name, case.patient.first_name, case.notes),
                         ("Web Identity", "Web Identity", "Current draft"))
        self.assertTrue(AuditEvent.objects.filter(patient_id=case.patient_id,
            action="patients.case.identity_mirrored").exists())
        url, data = self.edit_page(case)
        with patch("patients.audit.record_audit_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(url, dict(data, first_name="Must Roll Back"))
        case.refresh_from_db()
        self.assertEqual((case.first_name, case.patient.first_name), ("Web Identity", "Web Identity"))

    def test_ordinary_validation_retry_preserves_draft_and_baseline(self):
        case = self.case(prefix="MRS", age=25, gender="FEMALE")
        url, data = self.edit_page(case)
        data.update(age="invalid", notes="Fix this draft")
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("age", response.context["form"].errors)
        self.assertEqual(response.context["form"]["notes"].value(), data["notes"])
        self.assertEqual(response.context["form"]["rendered_baseline"].value(), data["rendered_baseline"])
        data["age"] = 25
        self.assertEqual(self.client.post(url, data).status_code, 302)


class WebPatientLockOrderTests(TransactionTestCase):
    client_class = fixtures.RenderedCaseBaselineTests.client_class
    setUp = fixtures.RenderedCaseBaselineTests.setUp
    case = fixtures.RenderedCaseBaselineTests.case
    edit_page = fixtures.RenderedCaseBaselineTests.edit_page

    def test_real_case_and_patient_posts_finish_without_deadlock_or_lost_identity(self):
        case = self.case(prefix="MRS", age=25, gender="FEMALE")
        url, data = self.edit_page(case)
        data["notes"] = "Stale concurrent draft"
        identity_client = self.client_class()
        identity_client.force_login(self.user)
        patient = Patient.objects.get(pk=case.patient_id)
        identity_data = {key: value if value is not None else ""
            for key, value in model_to_dict(patient, fields=PatientForm.Meta.fields).items()}
        identity_data["first_name"] = "Concurrent Identity"
        patient_locked, web_lock_attempt = Event(), Event()

        def identity_hook(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if 'FROM "patients_patient"' in sql and "FOR UPDATE" in sql and not patient_locked.is_set():
                patient_locked.set()
                self.assertTrue(web_lock_attempt.wait(5), "web edit did not reach its first row lock")
            return result

        def web_hook(execute, sql, params, many, context):
            if "FOR UPDATE" in sql and not web_lock_attempt.is_set():
                if 'FROM "patients_patient"' in sql:
                    # The corrected writer waits for Patient without holding Case.
                    web_lock_attempt.set()
                elif 'FROM "patients_case"' in sql:
                    # The old writer holds Case before the other request asks for it.
                    result = execute(sql, params, many, context)
                    web_lock_attempt.set()
                    return result
            return execute(sql, params, many, context)

        def post(client, route, payload, hook, wait_for_patient=False):
            close_old_connections()
            try:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                if wait_for_patient:
                    self.assertTrue(patient_locked.wait(5), "patient edit did not acquire Patient")
                with connections["default"].execute_wrapper(hook):
                    return client.post(route, payload)
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            identity = pool.submit(post, identity_client,
                reverse("patients:patient_edit", args=[patient.pk]), identity_data, identity_hook)
            web = pool.submit(post, self.client, url, data, web_hook, True)
            identity_response, web_response = identity.result(timeout=15), web.result(timeout=15)
        self.assertEqual(identity_response.status_code, 302)
        self.assertContains(web_response, "This case changed while you were editing.")
        self.assertEqual(web_response.context["form"]["notes"].value(), data["notes"])
        self.assertEqual(web_response.context["form"]["rendered_baseline"].value(), data["rendered_baseline"])
        case.refresh_from_db()
        patient.refresh_from_db()
        self.assertEqual((case.first_name, patient.first_name), ("Concurrent Identity", "Concurrent Identity"))
        self.assertNotEqual(case.notes, data["notes"])
        self.assertTrue(AuditEvent.objects.filter(patient_id=patient.pk, action="patient.identity_updated").exists())
