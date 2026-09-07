"""Synthetic regression coverage for issue #113 Stage 1."""
from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .database_bundle import create_bundle_archive, import_bundle_bytes
from .follow_up import attention_filter
from .models import Case, CaseDataScope, CaseStatus, DepartmentConfig, RoleSetting, Task, TaskStatus
from .test_client import AuthVersionTestClient


class FollowUpTests(TestCase):
    client_class = AuthVersionTestClient

    def setUp(self):
        self.user = get_user_model().objects.create_superuser("stage113", password="synthetic-test-only")
        self.anc, _ = DepartmentConfig.objects.get_or_create(name="ANC")
        self.medicine, _ = DepartmentConfig.objects.get_or_create(name="Medicine")
        self.today = timezone.localdate()
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.client.force_login(self.user)

    def case(self, **values):
        defaults = dict(uhid=f"SYNTH-{Case.objects.count()}", first_name="Synthetic", last_name="Case",
            phone_number="9000000001", category=self.anc, created_by=self.user,
            edd=self.today - timedelta(days=1), lmp=self.today - timedelta(days=281), rch_bypass=True)
        defaults.update(values)
        return Case.objects.create(**defaults)

    def task(self, case, status=TaskStatus.SCHEDULED, **values):
        return Task.objects.create(case=case, title="Synthetic task", due_date=self.today - timedelta(days=2),
            status=status, created_by=self.user, **values)

    def action(self, case, **values):
        data = dict(action="outcome", base_updated_at=case.updated_at.isoformat(), reason="Verified synthetic outcome",
            outcome="delivery", outcome_date=self.today.isoformat(), continue_follow_up="close",
            task_policy="retain", client_write_id=f"anc-{case.pk}")
        data.update(values)
        return self.api.post(reverse("api:anc_action", args=[case.pk]), data, format="json")

    def ids(self, bucket):
        return set(attention_filter(Case.objects.all(), bucket).values_list("pk", flat=True))

    def test_yesterday_zero_tasks_is_overdue_today_is_dormant_and_missing_is_explicit(self):
        yesterday = self.case()
        today = self.case(edd=self.today)
        missing = self.case(edd=None, lmp=None)
        self.assertEqual(self.ids("overdue"), {yesterday.pk})
        self.assertEqual(self.ids("dormant"), {today.pk, missing.pk})
        self.assertEqual(self.ids("edd_missing"), {missing.pk})
        self.assertTrue(missing.follow_up["edd_missing"])

    def test_future_correction_of_taskless_case_removes_edd_overdue(self):
        case = self.case()
        response = self.action(case, action="correct_edd", usg_edd=(self.today + timedelta(days=20)).isoformat())
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn(case.pk, self.ids("overdue"))
        self.assertIn(case.pk, self.ids("dormant"))

    def test_post_search_uses_same_predicates_and_additive_old_list_contract(self):
        overdue = self.case()
        dormant = self.case(edd=self.today)
        self.task(dormant, TaskStatus.COMPLETED)
        for bucket, expected in (("overdue", overdue.pk), ("dormant", dormant.pk)):
            response = self.api.post(reverse("api:case_search"), {"query": "Synthetic", "bucket": bucket}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual([row["id"] for row in response.data["results"]], [expected])
            self.assertEqual(response.data["stats"][bucket], 1)
        legacy = self.api.get(reverse("api:case_list"), {"bucket": "all"})
        self.assertTrue({"count", "next", "previous", "stats", "results"}.issubset(legacy.data))
        self.assertTrue({"id", "name", "status", "next_task", "task_counts"}.issubset(legacy.data["results"][0]))

    def test_open_completed_cancelled_mixed_tasks_and_api_counts_agree(self):
        case = self.case(category=self.medicine, edd=None)
        self.task(case, TaskStatus.COMPLETED)
        self.task(case, TaskStatus.CANCELLED)
        pending = self.task(case, TaskStatus.AWAITING_REPORTS)
        self.assertIn(case.pk, self.ids("overdue"))
        self.assertNotIn(case.pk, self.ids("dormant"))
        response = self.api.get(reverse("api:case_list"), {"bucket": "overdue"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["stats"]["overdue"], response.data["count"])
        self.assertEqual(response.data["count"], 1)
        pending.status = TaskStatus.CANCELLED
        pending.save()
        self.assertEqual(self.ids("overdue"), set())
        self.assertEqual(self.ids("dormant"), {case.pk})

    def test_patient_group_retains_affected_case_when_sibling_has_open_task(self):
        dormant = self.case(edd=self.today)
        sibling = self.case(uhid=dormant.uhid, patient=dormant.patient, category=self.medicine)
        self.task(sibling)
        another = self.case(uhid=dormant.uhid, patient=dormant.patient, category=self.medicine)
        response = self.client.get(reverse("patients:follow_up_list"), {"bucket": "dormant"})
        self.assertEqual(response.context["case_count"], 2)
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertEqual({c.pk for c in response.context["patient_groups"][0]["cases"]}, {dormant.pk, another.pk})

    def test_future_correction_audited_retains_generated_manual_and_completed_tasks(self):
        case = self.case()
        tasks = [self.task(case), self.task(case, TaskStatus.COMPLETED), self.task(case, notes="Manual change")]
        before = [(t.pk, t.due_date, t.status) for t in tasks]
        future = self.today + timedelta(days=10)
        response = self.action(case, action="correct_edd", usg_edd=future.isoformat())
        self.assertEqual(response.status_code, 200, response.data)
        case.refresh_from_db()
        self.assertEqual(case.effective_edd, future)
        self.assertFalse(case.follow_up["edd_overdue"])
        self.assertEqual(before, list(case.tasks.order_by("pk").values_list("pk", "due_date", "status")))
        log = case.activity_logs.get(note__contains="USG EDD corrected")
        self.assertEqual(log.user_id, self.user.pk)
        self.assertIn(str(future), log.note)
        self.assertIn("Reason:", log.note)

    def test_resolution_explicit_cancellation_preserves_completed_history_and_replay(self):
        case = self.case()
        selected = self.task(case)
        retained = self.task(case)
        completed = self.task(case, TaskStatus.COMPLETED)
        values = dict(task_policy="cancel_selected", cancel_task_ids=[selected.pk])
        response = self.action(case, **values)
        self.assertEqual(response.status_code, 200, response.data)
        count = case.activity_logs.count()
        self.assertEqual(self.action(case, **values).status_code, 200)
        self.assertEqual(case.activity_logs.count(), count)
        case.refresh_from_db(); selected.refresh_from_db(); retained.refresh_from_db(); completed.refresh_from_db()
        self.assertEqual((case.status, case.anc_outcome), (CaseStatus.COMPLETED, "delivery"))
        self.assertEqual(selected.status, TaskStatus.CANCELLED)
        self.assertEqual(retained.status, TaskStatus.SCHEDULED)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertIn(case.pk, self.ids("overdue"))
        self.assertFalse(case.follow_up["edd_overdue"])

    def test_referral_continuation_records_resolution_without_closing_case(self):
        case = self.case()
        response = self.action(case, outcome="referral", referral_destination="Synthetic clinic", continue_follow_up="continue")
        self.assertEqual(response.status_code, 200, response.data)
        case.refresh_from_db()
        self.assertEqual(case.status, CaseStatus.ACTIVE)
        self.assertEqual(case.anc_referral_destination, "Synthetic clinic")
        self.assertFalse(case.follow_up["edd_overdue"])
        self.assertTrue(case.follow_up["dormant"])

    def test_blank_reason_future_outcome_and_missing_referral_choice_are_invalid(self):
        for values in ({"reason": "  "}, {"outcome_date": (self.today + timedelta(days=1)).isoformat()},
                       {"outcome": "referral"}, {"continue_follow_up": ""}):
            with self.subTest(values=values):
                response = self.action(self.case(), **values)
                self.assertEqual(response.status_code, 400, response.data)

    def test_cross_case_task_and_stale_case_are_rejected(self):
        case = self.case()
        other_task = self.task(self.case())
        self.assertEqual(self.action(case, task_policy="cancel_selected", cancel_task_ids=[other_task.pk]).status_code, 400)
        case.notes = "Concurrent change"; case.save()
        old_stamp = case.updated_at - timedelta(minutes=1)
        self.assertEqual(self.action(case, base_updated_at=old_stamp.isoformat(), client_write_id="stale").status_code, 409)
        case.refresh_from_db()
        self.assertEqual(case.anc_outcome, "")

    def test_scoped_taskless_creator_visible_but_forbidden_ids_and_counts_stay_hidden(self):
        staff = get_user_model().objects.create_user("scoped")
        group = Group.objects.create(name="Stage113Assigned")
        RoleSetting.objects.create(role_name=group.name, case_data_scope=CaseDataScope.ASSIGNED, can_case_edit=True)
        staff.groups.add(group)
        own = self.case(created_by=staff)
        hidden = self.case()
        self.api.force_authenticate(staff)
        response = self.api.get(reverse("api:case_list"), {"bucket": "overdue"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([r["id"] for r in response.data["results"]], [own.pk])
        self.assertEqual(response.data["stats"]["overdue"], 1)
        self.assertEqual(self.action(hidden).status_code, 404)
        self.client.force_login(staff)
        dashboard = self.client.get(reverse("patients:dashboard"))
        self.assertEqual(dashboard.context["active_case_count"], 1)

    def test_case_editor_without_task_edit_can_retain_but_cannot_cancel(self):
        staff = get_user_model().objects.create_user("editor")
        group = Group.objects.create(name="Stage113Editor")
        RoleSetting.objects.create(role_name=group.name, case_data_scope=CaseDataScope.ALL, can_case_edit=True, can_task_edit=False)
        staff.groups.add(group)
        self.api.force_authenticate(staff)
        case = self.case(); task = self.task(case)
        self.assertEqual(self.action(case, task_policy="cancel_selected", cancel_task_ids=[task.pk]).status_code, 403)
        self.assertEqual(self.action(case, client_write_id="retained").status_code, 200)

    def test_closed_and_archived_history_not_reopened(self):
        closed = self.case(status=CaseStatus.COMPLETED)
        archived = self.case(is_archived=True)
        self.assertEqual(self.ids("overdue"), set())
        self.assertEqual(self.ids("dormant"), set())
        closed.refresh_from_db(); archived.refresh_from_db()
        self.assertEqual(closed.status, CaseStatus.COMPLETED)
        self.assertTrue(archived.is_archived)

    def test_bundle_roundtrip_preserves_resolution_fields(self):
        case = self.case()
        self.assertEqual(self.action(case, outcome="referral", referral_destination="Synthetic clinic").status_code, 200)
        archive, _, _ = create_bundle_archive()
        with TemporaryDirectory() as directory, patch("patients.database_bundle.default_backup_dir", return_value=__import__('pathlib').Path(directory)):
            import_bundle_bytes(archive)
        restored = Case.objects.get(uhid=case.uhid)
        self.assertEqual(restored.anc_outcome, "referral")
        self.assertEqual(restored.anc_outcome_date, self.today)
        self.assertEqual(restored.anc_referral_destination, "Synthetic clinic")
        self.assertFalse(restored.anc_continue_follow_up)

    def test_web_action_preview_lists_open_tasks_and_post_records_outcome(self):
        case = self.case(); task = self.task(case)
        response = self.client.get(reverse("patients:anc_action", args=[case.pk]))
        self.assertContains(response, task.title)
        self.assertContains(response, "retain all task dates", html=False)
        response = self.client.post(reverse("patients:anc_action", args=[case.pk]), dict(
            action="outcome", base_updated_at=case.updated_at.isoformat(), reason="Synthetic delivery",
            outcome="delivery", outcome_date=self.today.isoformat(), continue_follow_up="close", task_policy="retain"))
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.anc_outcome, "delivery")
