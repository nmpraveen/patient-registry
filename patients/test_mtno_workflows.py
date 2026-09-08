from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.views import _case_edit_payload
from .forms import CaseForm, PatientMergeConfirmationForm
from .merge_recovery import recover_patient_merge
from .models import Case, CaseDataScope, DepartmentConfig, Patient, PatientMergeRecovery, RoleSetting, Task, ensure_default_departments
from .test_client import AuthVersionTestClient
from .views import _build_upcoming_call_queue, _merge_patient_records, _patient_search_queryset


class MtnoWorkflowTests(TestCase):
    client_class = AuthVersionTestClient

    def setUp(self):
        ensure_default_departments()
        self.admin = get_user_model().objects.create_superuser(username="mtno-admin", password="synthetic-password")
        self.category = DepartmentConfig.objects.get(name="Surgery")
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.client.force_login(self.admin)

    def payload(self, **overrides):
        return dict(patient_mode="new", prefix="MR", first_name="Synthetic", last_name="Example",
                    age=35, phone_number="9000000001", category=self.category.pk,
                    subcategory="GENERAL_SURGERY", surgical_pathway="SURVEILLANCE", review_date=str(timezone.localdate() + timedelta(days=5)),
                    **overrides)

    def create_case(self, **overrides):
        form = CaseForm(data=self.payload(**overrides), actor=self.admin)
        form.instance.created_by = self.admin
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def test_blank_uhid_intake_shared_case_and_later_assignment(self):
        first = self.create_case()
        identity = first.mtno
        second = self.create_case(selected_patient=first.patient_id)
        # A new blank-UHID registration is a distinct patient, never blank-key deduplication.
        self.assertNotEqual(first.patient_id, second.patient_id)
        payload = self.payload()
        payload.update(patient_mode="existing", selected_patient=first.patient_id)
        form = CaseForm(data=payload, actor=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        shared = form.save()
        self.assertEqual(shared.mtno, identity)
        first.patient.uhid = "HOSP-987"
        first.patient.save()
        for case in (first, shared):
            case.refresh_from_db()
            self.assertEqual((case.mtno, case.uhid), (identity, "HOSP-987"))

    def test_tmp_is_preserved_on_unrelated_edit_and_explicit_uhid_assignment(self):
        case = self.create_case(use_temporary_uhid=True)
        original = case.uhid, case.mtno
        data = _case_edit_payload(case)
        data["diagnosis"] = "Updated synthetic diagnosis"
        form = CaseForm(data=data, instance=case, actor=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual((saved.uhid, saved.mtno), original)
        data = _case_edit_payload(saved)
        data["uhid"] = "HOSP-NEW"
        # Even a legacy true flag cannot erase an explicit newly supplied hospital identifier.
        form = CaseForm(data=data, instance=saved, actor=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual((saved.uhid, saved.mtno), ("HOSP-NEW", original[1]))

    def test_api_allocates_readonly_mtno_and_blank_uhid_paginates(self):
        identities = []
        for index in range(3):
            response = self.api.post(reverse("api:case_list"), self.payload(client_write_id=f"mtno-new-{index}"), format="json")
            self.assertEqual(response.status_code, 201, response.content)
            row = response.json()["case"]
            self.assertEqual(row["uhid"], "")
            identities.append(row["mtno"])
        cursor, rows = None, []
        for _ in range(3):
            data = {"query": "Synthetic", "page_size": 1}
            if cursor:
                data["cursor"] = cursor
            response = self.api.post(reverse("api:patient_search"), data, format="json")
            self.assertEqual(response.status_code, 200, response.content)
            rows.extend(response.json()["results"])
            cursor = response.json()["next_cursor"]
        self.assertIsNone(cursor)
        self.assertEqual({row["mtno"] for row in rows}, set(identities))
        response = self.api.post(reverse("api:case_list"), self.payload(mtno="MT-009999"), format="json")
        self.assertEqual(response.status_code, 400)
        case = Case.objects.first()
        response = self.api.patch(reverse("api:case_detail", args=[case.pk]), {"mtno":"MT-009999"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_merge_alias_search_and_recovery_preserve_identity_and_clinical_fields(self):
        source_case = self.create_case(uhid="HOSP-SOURCE")
        target_case = self.create_case()
        source, target = source_case.patient, target_case.patient
        original = source.mtno, target.mtno
        source_case.anc_outcome_reason = "Existing history remains"
        Case.objects.filter(pk=source_case.pk).update(anc_outcome_reason=source_case.anc_outcome_reason)
        _merge_patient_records(source_patient=source, target_patient=target, actor=self.admin)
        source.refresh_from_db()
        target.refresh_from_db()
        source_case.refresh_from_db()
        self.assertEqual((source.mtno, target.mtno), original)
        self.assertEqual(source_case.mtno, target.mtno)
        for query in (source.mtno, source.uhid):
            self.assertEqual(list(_patient_search_queryset(query, user=self.admin).values_list("pk", flat=True)), [target.pk])
            response = self.api.post(reverse("api:patient_search"), {"query":query}, format="json")
            self.assertEqual(response.json()["results"], [{"id":target.pk,"mtno":target.mtno,"uhid":"","name":target.full_name}])
            response = self.client.get(reverse("patients:universal_case_search"), {"q":query})
            self.assertEqual(response.status_code, 200, response.content)
            self.assertIn(target.mtno, response.content.decode())
        recovery = PatientMergeRecovery.objects.get(source_patient=source)
        recover_patient_merge(recovery_id=recovery.recovery_id, actor=self.admin)
        source_case.refresh_from_db()
        self.assertEqual(source_case.mtno, original[0])
        self.assertEqual(source_case.anc_outcome_reason, "Existing history remains")
        self.assertEqual(list(_patient_search_queryset(source.mtno, user=self.admin).values_list("pk", flat=True)), [source.pk])

    def test_alias_forbidden_lookup_and_selection_reveal_no_identity(self):
        source, target = self.create_case().patient, self.create_case().patient
        _merge_patient_records(source_patient=source, target_patient=target, actor=self.admin)
        actor = get_user_model().objects.create_user(username="mtno-restricted")
        role = RoleSetting.objects.create(role_name="MTNO Assigned", case_data_scope=CaseDataScope.ASSIGNED,
                                          can_case_create=True, can_intake_patient_lookup=True)
        actor.groups.add(Group.objects.create(name=role.role_name))
        api = APIClient()
        api.force_authenticate(actor)
        response = api.post(reverse("api:patient_search"), {"query": source.mtno}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["results"], [])
        data = self.payload()
        data.update(patient_mode="existing", selected_patient=target.pk)
        response = api.post(reverse("api:case_list"), data, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(target.mtno, response.content.decode())

    def test_merge_confirmation_requires_target_mtno_even_without_uhid(self):
        source, target = self.create_case().patient, self.create_case().patient
        form = PatientMergeConfirmationForm(data={"target_patient":target.pk,"confirm_target_uhid":target.mtno,"confirm_merge":True},
            source_patient=source, target_patient=target, target_queryset=Patient.objects.all())
        self.assertTrue(form.is_valid(), form.errors)

    def test_quick_web_entry_has_mtno_without_manufactured_uhid(self):
        response = self.client.post(reverse("patients:case_quick_create"), {"prefix":"MR","first_name":"Synthetic",
            "age":40,"gender":"MALE","category":self.category.pk,"diagnosis":"Synthetic review","review_date":str(timezone.localdate())})
        self.assertEqual(response.status_code, 302, response.context["form"].errors if response.context else response.status_code)
        case = Case.objects.get()
        self.assertTrue(case.mtno.startswith("MT-"))
        self.assertEqual(case.uhid, "")

    def test_blank_uhid_clinical_pages_show_permanent_identity(self):
        case = self.create_case()
        for route in ("case_vitals", "vitals_create"):
            response = self.client.get(reverse("patients:" + route, args=[case.pk]))
            self.assertContains(response, case.mtno)
        case.category = DepartmentConfig.objects.get(name="ANC")
        case.metadata = {"entry_mode": "quick_entry"}
        case.save()
        response = self.client.get(reverse("patients:anc_action", args=[case.pk]))
        self.assertContains(response, case.mtno)

    def test_call_queue_identity_queries_stay_constant_as_cases_grow(self):
        today = timezone.localdate()
        filters = {"range_start": today, "range_end": today}
        first = self.create_case()
        Task.objects.create(case=first, title="Synthetic call", due_date=today)
        with CaptureQueriesContext(connection) as small:
            first_rows = _build_upcoming_call_queue(filters)["rows"]
        self.assertEqual(first_rows[0]["mtno"], first.mtno)
        for _ in range(6):
            case = self.create_case()
            Task.objects.create(case=case, title="Synthetic call", due_date=today)
        with CaptureQueriesContext(connection) as large:
            rows = _build_upcoming_call_queue(filters)["rows"]
        self.assertEqual(len(rows), 7)
        self.assertEqual(len(large), len(small))
        self.assertTrue(all(row["mtno"] and row["uhid"] == "" for row in rows))

    def test_intake_rejects_uhid_in_permanent_number_namespace(self):
        original = self.create_case()
        response = self.api.post(reverse("api:case_list"), self.payload(uhid=original.mtno), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Patient.objects.count(), 1)
        response = self.api.patch(reverse("api:case_detail", args=[original.pk]), {
            "uhid": original.mtno, "base_values": {"uhid": ""},
            "base_updated_at": original.updated_at.isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Case.objects.filter(pk=original.pk).update(uhid=original.mtno)
        original.refresh_from_db()
        self.assertEqual(original.uhid, "")
