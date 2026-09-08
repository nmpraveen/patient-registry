from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import MobileDatasetState
from api.stage4_views import case_timeline_payload
from .models import AuditEvent, CallLog, CallOutcome, Case, CaseActivityLog, CaseDataScope, DepartmentConfig, RoleSetting, Task, TaskStatus
from .timeline import timeline_page
from .test_client import AuthVersionTestClient


class Stage4ScreenTests(TestCase):
    client_class = AuthVersionTestClient
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("stage4", "", "synthetic-password")
        cls.category = DepartmentConfig.objects.get(name="Surgery")
        cls.case = Case.objects.create(uhid="S4-SYNTHETIC", first_name="Synthetic", last_name="Stagefour",
                                      category=cls.category, created_by=cls.user)

    def setUp(self):
        self.client.force_login(self.user)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def activity(self, event_type="NOTE", **kwargs):
        return CaseActivityLog.objects.create(case=self.case, event_type=event_type, user=self.user,
                                               note="Synthetic history", **kwargs)

    def test_timeline_same_timestamp_cross_source_pages_no_duplicates_and_new_insert_excluded(self):
        stamp = timezone.now()
        for _ in range(35):
            self.activity()
        for _ in range(5):
            CallLog.objects.create(case=self.case, outcome=CallOutcome.NO_ANSWER, staff_user=self.user, reason="Check visit")
        self.case.activity_logs.update(created_at=stamp)
        self.case.call_logs.update(created_at=stamp)
        entries, pos, snapshot = timeline_page(self.case)
        self.assertEqual(len(entries), 30)
        self.assertTrue(all(entry["id"].startswith("call:") for entry in entries[:5]))
        added = self.activity()
        added_id = f"activity:{added.pk}"
        self.case.activity_logs.filter(pk=added.pk).update(created_at=stamp - timedelta(days=1))
        older, final_pos, _ = timeline_page(self.case, position=pos, snapshot=snapshot)
        ids = [entry["id"] for entry in entries + older]
        self.assertEqual(len(ids), 40)
        self.assertEqual(len(set(ids)), 40)
        self.assertNotIn(added_id, ids)
        self.assertIsNone(final_pos)

    def test_filters_canonical_calls_task_notes_and_clinical(self):
        task = Task.objects.create(case=self.case, title="Review", due_date=timezone.localdate(), created_by=self.user)
        call = CallLog.objects.create(case=self.case, outcome=CallOutcome.NO_ANSWER, reason="General reason",
                                     notes="Details", staff_user=self.user)
        self.activity("CALL")
        note = CaseActivityLog.objects.create(case=self.case, event_type="TASK", task=task, user=self.user,
                                              note="Task note updated: sample")
        task_edit = self.activity("TASK", task=task)
        clinical = self.activity("SYSTEM")
        self.assertEqual([e["id"] for e in timeline_page(self.case, filter_key="calls")[0]], [f"call:{call.pk}"])
        self.assertEqual([e["id"] for e in timeline_page(self.case, filter_key="notes")[0]], [f"activity:{note.pk}"])
        self.assertEqual([e["id"] for e in timeline_page(self.case, filter_key="tasks")[0]], [f"activity:{task_edit.pk}"])
        self.assertEqual([e["id"] for e in timeline_page(self.case, filter_key="clinical")[0]], [f"activity:{clinical.pk}"])
        self.assertEqual(len(timeline_page(self.case)[0]), 4)

    def test_cursor_binds_filter_actor_and_dataset_epoch(self):
        for _ in range(31):
            self.activity()
        payload = case_timeline_payload(self.case, self.user, filter_key="all")
        cursor = payload["next_cursor"]
        url = reverse("api:case_timeline", args=[self.case.pk])
        self.assertEqual(self.api.get(url, {"filter": "notes", "cursor": cursor}).status_code, 400)
        other = get_user_model().objects.create_superuser("stage4other", "", "synthetic-password")
        self.api.force_authenticate(other)
        self.assertEqual(self.api.get(url, {"cursor": cursor}).status_code, 400)
        self.api.force_authenticate(self.user)
        import uuid
        MobileDatasetState.objects.filter(pk=1).update(epoch=uuid.uuid4())
        self.assertEqual(self.api.get(url, {"cursor": cursor}).status_code, 400)

    def test_unauthorized_read_and_invalid_filter(self):
        outsider = get_user_model().objects.create_user("outsider-stage4")
        self.api.force_authenticate(outsider)
        self.assertIn(self.api.get(reverse("api:case_timeline", args=[self.case.pk])).status_code, [403, 404])
        self.assertEqual(self.api.get(reverse("api:upcoming_tasks")).status_code, 403)
        self.api.force_authenticate(self.user)
        self.assertEqual(self.api.get(reverse("api:case_timeline", args=[self.case.pk]), {"filter": "bad"}).status_code, 400)

    def test_upcoming_inclusive_seven_days_later_dates_and_same_title_group(self):
        today = timezone.localdate()
        for offset in [-1, 0, 0, 6, 7]:
            Task.objects.create(case=self.case, title="Same title", due_date=today + timedelta(days=offset),
                                assigned_user=self.user, created_by=self.user)
        Task.objects.create(case=self.case, title="Completed", due_date=today, status=TaskStatus.COMPLETED, created_by=self.user)
        result = self.api.get(reverse("api:upcoming_tasks"))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.data["results"]), 3)
        self.assertEqual(result.data["start_date"], today.isoformat())
        self.assertEqual(result.data["end_date"], (today + timedelta(days=6)).isoformat())
        self.assertEqual(len(self.api.get(reverse("api:upcoming_tasks"), {"start_date": (today + timedelta(days=7)).isoformat()}).data["results"]), 1)
        page = self.client.get(reverse("patients:dashboard"))
        self.assertEqual(page.context["selected_week_start"], today)
        row = page.context["appointment_schedule_days"][0]["rows"][0]
        self.assertEqual(row["task_count"], 2)
        self.assertContains(page, "2 tasks")
        self.assertContains(page, "Later dates")
        self.assertContains(page, "stage4")

    def test_upcoming_pagination_and_filter_bound_cursor(self):
        for index in range(55):
            Task.objects.create(case=self.case, title=f"Task {index}", due_date=timezone.localdate(), created_by=self.user)
        url = reverse("api:upcoming_tasks")
        first = self.api.get(url).data
        self.assertEqual(len(first["results"]), 50)
        second = self.api.get(url, {"cursor": first["next_cursor"]}).data
        self.assertEqual(len(second["results"]), 5)
        self.assertIsNone(second["next_cursor"])
        self.assertFalse({r["id"] for r in first["results"]} & {r["id"] for r in second["results"]})
        self.assertEqual(self.api.get(url, {"cursor": first["next_cursor"], "category": "ANC"}).status_code, 400)

    def test_upcoming_search_body_and_filters(self):
        Task.objects.create(case=self.case, title="Review", due_date=timezone.localdate(), created_by=self.user)
        url = reverse("api:upcoming_search")
        self.assertEqual(len(self.api.post(url, {"query": "Synthetic", "category": ["Surgery"]}, format="json").data["results"]), 1)
        self.assertEqual(len(self.api.post(url, {"query": "Synthetic", "category": ["ANC"]}, format="json").data["results"]), 0)
        self.assertEqual(self.api.post(url + "?query=Synthetic", {"query": "Synthetic"}, format="json").status_code, 400)
        self.assertEqual(self.api.get(reverse("api:upcoming_tasks"), {"query": "Synthetic"}).status_code, 400)
        denied = AuditEvent.objects.filter(action="case.search_attempt", outcome=AuditEvent.Outcome.DENIED).last()
        self.assertIsNotNone(denied)
        self.assertNotIn("Synthetic", str(denied.metadata))

    def test_web_timeline_expanded_bounded_and_navigation(self):
        for _ in range(33):
            self.activity()
        page = self.client.get(reverse("patients:case_detail", args=[self.case.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.context["timeline_entries"]), 30)
        self.assertFalse(page.context["timeline_collapsed"])
        self.assertContains(page, "Older entries")
        self.assertContains(page, "Selected case")
        self.assertContains(page, "Next action:")

    def test_intake_has_one_save_and_optional_details(self):
        page = self.client.get(reverse("patients:case_create"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-case-submit-button", count=1)
        self.assertContains(page, '<details class="case-create-card case-create-optional">')
        self.assertContains(page, 'id="case-create-form"')

    def test_related_cases_are_patient_specific_and_scoped(self):
        sibling = Case.objects.create(patient=self.case.patient, uhid=self.case.uhid, category=self.category,
                                      first_name="Synthetic", last_name="Stagefour", created_by=self.user)
        unrelated = Case.objects.create(uhid="S4-OTHER", category=self.category, first_name="Different", created_by=self.user)
        url = reverse("api:related_cases", args=[self.case.pk])
        response = self.api.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.data["results"]}, {self.case.pk, sibling.pk})
        self.assertNotIn(unrelated.pk, {row["id"] for row in response.data["results"]})
        restricted = get_user_model().objects.create_user("stage4-scoped")
        role = RoleSetting.objects.create(role_name="stage4-scoped", case_data_scope=CaseDataScope.ASSIGNED)
        group = Group.objects.create(name=role.role_name)
        restricted.groups.add(group)
        Task.objects.create(case=self.case, title="Assigned", due_date=timezone.localdate(), assigned_user=restricted, created_by=self.user)
        self.api.force_authenticate(restricted)
        result = self.api.get(url)
        self.assertEqual(result.status_code, 200)
        self.assertEqual([row["id"] for row in result.data["results"]], [self.case.pk])
        self.assertEqual(self.api.get(reverse("api:related_cases", args=[sibling.pk])).status_code, 404)

    def test_web_call_summary_preserves_all_failure_count_with_bounded_history(self):
        task = Task.objects.create(case=self.case, title="Follow-up", due_date=timezone.localdate(), created_by=self.user)
        for _ in range(45):
            CallLog.objects.create(case=self.case, task=task, outcome=CallOutcome.NO_ANSWER, staff_user=self.user)
        page = self.client.get(reverse("patients:case_detail", args=[self.case.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["call_summary"]["failed_attempt_count"], 45)
        self.assertEqual(len(page.context["timeline_entries"]), 30)
        self.assertEqual(page.context["tasks"][0].latest_call_summary["outcome"], "No answer")
