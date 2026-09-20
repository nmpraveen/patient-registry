"""Behavior regressions from the whole-project review, using synthetic records."""
from datetime import date, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .database_bundle import BundleValidationError, create_bundle_archive, load_bundle_archive, write_backup_bundle
from .models import Case, CaseDataScope, DepartmentConfig, Patient, RoleSetting, Task, TaskStatus
from .presentation import current_age
from .recent_cases import notes_baseline
from .test_client import AuthVersionTestClient
from .views import (_patient_case_rows, _patient_queryset, _patient_search_queryset,
                    _serialize_patient_search_result, _recent_case_payload_for_id)


class ReviewRemediationTests(TestCase):
    client_class = AuthVersionTestClient

    def setUp(self):
        self.user = get_user_model().objects.create_superuser("review", password="synthetic-only-password")
        self.category, _ = DepartmentConfig.objects.get_or_create(name="Medicine")
        self.client.force_login(self.user)

    def case(self, **values):
        fields = dict(first_name="Synthetic", last_name=str(Case.objects.count()),
                      uhid=f"REVIEW-{Case.objects.count()}", phone_number="9000000001",
                      category=self.category, subcategory="GENERAL_MEDICINE",
                      review_date=timezone.localdate(), diagnosis="Original", notes="Original notes", created_by=self.user)
        fields.update(values)
        return Case.objects.create(**fields)

    def test_notes_save_cannot_overwrite_new_diagnosis(self):
        case = self.case()
        token = notes_baseline(case, self.user)
        case.diagnosis = "New clinician correction"
        case.save(update_fields=["diagnosis", "updated_at"])
        response = self.client.post(reverse("patients:recent_case_update", args=[case.pk]),
            {"notes": "New note", "diagnosis": "Original", "notes_baseline": token})
        self.assertEqual(response.status_code, 200, response.content)
        case.refresh_from_db()
        self.assertEqual((case.diagnosis, case.notes), ("New clinician correction", "New note"))
        self.assertIn("notes_baseline", response.json()["case"])

    def test_conflicting_notes_and_wrong_actor_baselines_do_not_write(self):
        case = self.case()
        token = notes_baseline(case, self.user)
        case.notes = "Other clinician note"
        case.save(update_fields=["notes", "updated_at"])
        route = reverse("patients:recent_case_update", args=[case.pk])
        response = self.client.post(route, {"notes": "Stale replacement", "notes_baseline": token})
        self.assertEqual(response.status_code, 409)
        for bad_token in ("tampered", ""):
            self.assertEqual(self.client.post(route, {"notes": "Discard", "notes_baseline": bad_token}).status_code, 400)
        other = get_user_model().objects.create_superuser("other-review", password="synthetic-only-password")
        self.assertEqual(self.client.post(route, {"notes": "Discard", "notes_baseline": notes_baseline(case, other)}).status_code, 400)
        case.refresh_from_db()
        self.assertEqual(case.notes, "Other clinician note")

    def test_recent_pagination_is_bounded_stable_and_actor_bound(self):
        created = [self.case() for _ in range(25)]
        route = reverse("patients:recent_cases")
        first = self.client.get(route, {"limit": 10}).json()
        second = self.client.get(route, {"limit": 10, "cursor": first["next_cursor"]}).json()
        third = self.client.get(route, {"limit": 10, "cursor": second["next_cursor"]}).json()
        ids = [row["id"] for page in (first, second, third) for row in page["results"]]
        self.assertEqual(ids, [case.pk for case in reversed(created)])
        self.assertIsNone(third["next_cursor"])
        self.assertNotIn("tasks", first["results"][0])
        self.assertEqual(len(self.client.get(route, {"limit": "all"}).json()["results"]), 20)
        self.assertEqual(self.client.get(route, {"cursor": "bad"}).status_code, 400)
        other = get_user_model().objects.create_superuser("other-review", password="synthetic-only-password")
        self.client.force_login(other)
        self.assertEqual(self.client.get(route, {"cursor": first["next_cursor"]}).status_code, 400)

    def test_recent_detail_queries_do_not_grow_per_task(self):
        case = self.case()
        for n in range(20):
            Task.objects.create(case=case, title=f"Synthetic {n}", assigned_user=self.user,
                due_date=timezone.localdate(), status=TaskStatus.COMPLETED if n % 2 else TaskStatus.SCHEDULED)
        with CaptureQueriesContext(connection) as captured:
            detail = _recent_case_payload_for_id(case.pk, self.user)
        self.assertEqual(len(captured), 2)
        self.assertEqual(len(detail["tasks"]), 20)
        self.assertTrue(all(row["assigned_user_label"] == "review" for row in detail["tasks"]))
        response = self.client.get(reverse("patients:recent_case_update", args=[case.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["case"]["tasks"]), 20)

    def test_due_range_requires_one_task_inside_range_and_validates_dates(self):
        outside = self.case()
        inside = self.case()
        for due in (date(2026, 1, 1), date(2026, 12, 1)):
            Task.objects.create(case=outside, title="Outside", due_date=due)
        Task.objects.create(case=inside, title="Inside", due_date=date(2026, 6, 15))
        response = self.client.get(reverse("patients:case_list"), {"due_start": "2026-06-01", "due_end": "2026-06-30"})
        self.assertEqual([row.pk for row in response.context["cases"]], [inside.pk])
        for filters in ({"due_start": "bad"}, {"due_start": "2026-06-30", "due_end": "2026-06-01"}):
            response = self.client.get(reverse("patients:case_list"), filters)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["filter_error"])
            self.assertEqual(list(response.context["cases"]), [])

    def test_age_advances_after_birthday_without_patient_save(self):
        with patch("patients.models.timezone.localdate", return_value=date(2025, 1, 1)):
            patient = Patient.objects.create(first_name="Synthetic birthday", date_of_birth=date(1990, 2, 1))
        patient.refresh_from_db()
        self.assertEqual(patient.age, 34)
        self.assertEqual(current_age(patient, today=date(2026, 2, 1)), 36)
        self.assertEqual(current_age(Patient(age=42)), 42)

    def test_patient_creator_sees_only_authorized_case_counts(self):
        role = RoleSetting.objects.create(role_name="Review assigned", case_data_scope=CaseDataScope.ASSIGNED)
        group = Group.objects.create(name=role.role_name)
        actor = get_user_model().objects.create_user("assigned-review")
        actor.groups.add(group)
        visible = self.case(created_by=actor)
        self.case(patient=visible.patient, uhid=visible.uhid)
        Task.objects.create(case=visible, assigned_user=actor, title="Assigned", due_date=timezone.localdate())
        patient = _patient_queryset(user=actor).get(pk=visible.patient_id)
        self.assertEqual((patient.case_count, patient.active_case_count), (1, 1))
        self.assertEqual(len(_patient_case_rows(patient, user=actor)), 1)
        result = _serialize_patient_search_result(
            _patient_search_queryset(user=actor).get(pk=visible.patient_id), user=actor)
        self.assertEqual((result["case_count"], result["active_case_count"]), (1, 1))

    def test_patient_search_queries_are_bounded_across_result_count(self):
        for _ in range(10):
            self.case()
        # Warm permission policy; measure the data path rather than request auth.
        from .policy import effective_role_policy
        effective_role_policy(self.user)
        def measured(limit):
            with CaptureQueriesContext(connection) as captured:
                records = list(_patient_search_queryset(user=self.user)[:limit])
                result = [_serialize_patient_search_result(record, user=self.user) for record in records]
            return len(captured), result
        one_count, one = measured(1)
        ten_count, ten = measured(10)
        self.assertEqual(one_count, ten_count)
        self.assertEqual(ten_count, 2)
        self.assertEqual((len(one), len(ten)), (1, 10))

    def test_highly_compressible_export_roundtrips_and_oversize_does_not_prune(self):
        self.case(notes="A" * 2_000_000)
        archive, _, _ = create_bundle_archive()
        _, payload = load_bundle_archive(archive)
        self.assertEqual(payload["cases"][0]["notes"], "A" * 2_000_000)
        with TemporaryDirectory() as directory:
            existing = Path(directory) / "previous-recovery.zip"
            existing.write_bytes(b"retained")
            with patch("patients.database_bundle.MAX_BUNDLE_EXPANDED_BYTES", 1000), patch(
                    "patients.database_bundle.prune_backup_bundles") as prune:
                with self.assertRaises(BundleValidationError):
                    write_backup_bundle(output_dir=directory)
                prune.assert_not_called()
            self.assertEqual(existing.read_bytes(), b"retained")
            self.assertEqual(list(Path(directory).glob(".patient-backup-*")), [])
