"""Acceptance regressions for the remaining six automated Stage 1 comments."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from api.views import _case_edit_payload
from .models import Case, CaseDataScope, CaseStatus, RoleSetting, TaskStatus
from .test_follow_up import FollowUpTests


class AncCommentFixTests(TestCase):
    client_class = FollowUpTests.client_class
    setUp = FollowUpTests.setUp
    case = FollowUpTests.case
    task = FollowUpTests.task
    action = FollowUpTests.action
    ids = FollowUpTests.ids

    def test_cancelled_grey_task_requires_reopen_permission_in_web_and_api(self):
        user = get_user_model().objects.create_user("comment-editor")
        group = Group.objects.create(name="CommentEditor")
        role = RoleSetting.objects.create(role_name=group.name, case_data_scope=CaseDataScope.ALL,
            can_case_edit=True, can_task_reopen=False)
        user.groups.add(group)
        self.api.force_authenticate(user)
        self.client.force_login(user)
        for outcome, follow_up in (("referral", "continue"), ("loss_to_follow_up", "close")):
            for route in ("web", "api"):
                with self.subTest(outcome=outcome, route=route):
                    case = self.case()
                    task = self.task(case, TaskStatus.CANCELLED)
                    type(task).objects.filter(pk=task.pk).update(due_date=self.today - timedelta(days=31))
                    data = dict(action="outcome", base_updated_at=case.updated_at.isoformat(), reason="Verified",
                        outcome=outcome, outcome_date=self.today.isoformat(), referral_destination="Synthetic clinic",
                        continue_follow_up=follow_up, task_policy="retain", client_write_id=f"grey-{case.pk}")
                    url = reverse("patients:anc_action" if route == "web" else "api:anc_action", args=[case.pk])
                    response = self.client.post(url, data) if route == "web" else self.api.post(url, data, format="json")
                    self.assertEqual(response.status_code, 403)
                    case.refresh_from_db()
                    self.assertEqual(case.anc_outcome, "")
                    self.assertFalse(case.activity_logs.filter(note__startswith="ANC outcome:").exists())
        role.can_task_reopen = True
        role.save()
        self.assertEqual(self.action(case, outcome="loss_to_follow_up").status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.CANCELLED)

    def test_web_and_api_reclassification_accept_initial_anc_dates(self):
        for route in ("web", "api"):
            with self.subTest(route=route):
                case = self.case(category=self.medicine, edd=None, lmp=None, prefix="MRS", age=25, gender="FEMALE")
                current = _case_edit_payload(case)
                changes = dict(category=str(self.anc.pk), lmp=(self.today - timedelta(days=200)).isoformat(),
                    edd=(self.today + timedelta(days=80)).isoformat())
                if route == "api":
                    response = self.api.patch(reverse("api:case_detail", args=[case.pk]), changes | {
                        "base_updated_at": case.updated_at.isoformat(), "base_values": {k: current[k] for k in changes},
                        "client_write_id": f"reclassify-{case.pk}"}, format="json")
                    self.assertEqual(response.status_code, 200, response.data)
                else:
                    data = {k: v if v is not None else "" for k, v in current.items()} | changes
                    data["rendered_baseline"] = self.client.get(reverse("patients:case_edit", args=[case.pk])).context["form"]["rendered_baseline"].value()
                    response = self.client.post(reverse("patients:case_edit", args=[case.pk]), data)
                    self.assertEqual(response.status_code, 302, getattr(response, "context", None))
                case.refresh_from_db()
                self.assertEqual(case.category_id, self.anc.pk)
                self.assertEqual(case.edd, self.today + timedelta(days=80))
                current = _case_edit_payload(case)
                response = self.api.patch(reverse("api:case_detail", args=[case.pk]), {
                    "edd": (self.today + timedelta(days=90)).isoformat(),
                    "base_updated_at": case.updated_at.isoformat(), "base_values": {"edd": current["edd"]},
                    "client_write_id": f"reject-correction-{case.pk}"}, format="json")
                self.assertEqual(response.status_code, 400)

    def test_group_pagination_materializes_only_selected_patients_and_legacy_cases(self):
        cases = [self.case(edd=self.today) for _ in range(30)]
        sibling = self.case(patient=cases[0].patient, uhid=cases[0].uhid, edd=self.today)
        # Preserve compatibility for genuinely unlinked historical case rows.
        Case.objects.filter(pk__in=[case.pk for case in cases[-2:]]).update(patient=None)
        seen = set()
        for number, expected_groups in ((1, 25), (2, 5)):
            hydrated_ids = []
            original_from_db = Case.from_db
            def capture_case(cls, db, fields, values):
                case = original_from_db(db, fields, values)
                hydrated_ids.append(case.pk)
                return case
            with CaptureQueriesContext(connection) as queries, patch.object(Case, "from_db", classmethod(capture_case)):
                response = self.client.get(reverse("patients:follow_up_list"), {"bucket": "dormant", "page": number})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["case_count"], 31)
            self.assertEqual(response.context["paginator"].count, 30)
            groups = response.context["patient_groups"]
            self.assertEqual(len(groups), expected_groups)
            page_ids = {case.pk for group in groups for case in group["cases"]}
            self.assertFalse(seen & page_ids)
            seen |= page_ids
            self.assertEqual(set(hydrated_ids), page_ids)
            self.assertEqual(len(hydrated_ids), len(page_ids))
            self.assertTrue(any("LIMIT " in query["sql"] and "legacy_case_id" in query["sql"] for query in queries))
        self.assertEqual(seen, {case.pk for case in cases} | {sibling.pk})

    def test_reclassification_cannot_overwrite_a_stored_effective_edd(self):
        from .forms import CaseForm
        case = self.case(category=self.medicine, prefix="MRS", age=25, gender="FEMALE")
        data = {k: v if v is not None else "" for k, v in _case_edit_payload(case).items()}
        data.update(category=str(self.anc.pk), edd=(self.today + timedelta(days=10)).isoformat())
        form = CaseForm(data, instance=case, actor=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("edd", form.errors)

    def test_closed_retained_today_upcoming_tasks_remain_until_explicit_completion(self):
        for bucket, offset in (("today", 0), ("upcoming", 2)):
            case = self.case()
            task = self.task(case)
            type(task).objects.filter(pk=task.pk).update(due_date=self.today + timedelta(days=offset))
            self.assertEqual(self.action(case).status_code, 200)
            for response in (
                self.api.get(reverse("api:case_list"), {"bucket": bucket}),
                self.api.post(reverse("api:case_search"), {"query": case.uhid, "bucket": bucket}, format="json"),
            ):
                self.assertEqual({row["id"] for row in response.data["results"]}, {case.pk})
                self.assertEqual(response.data["stats"][bucket], 1)
            type(task).objects.filter(pk=task.pk).update(status=TaskStatus.COMPLETED)
            response = self.api.get(reverse("api:case_list"), {"bucket": "all"})
            self.assertNotIn(case.pk, {row["id"] for row in response.data["results"]})

    def test_closed_retained_tasks_stay_visible_in_scoped_list_search_and_counts(self):
        user = get_user_model().objects.create_user("retained-scoped")
        group = Group.objects.create(name="RetainedScoped")
        RoleSetting.objects.create(role_name=group.name, case_data_scope=CaseDataScope.ASSIGNED, can_case_edit=True)
        user.groups.add(group)
        for outcome in ("delivery", "loss_to_follow_up"):
            for task_status in (TaskStatus.SCHEDULED, TaskStatus.AWAITING_REPORTS):
                with self.subTest(outcome=outcome, task_status=task_status):
                    case = self.case(created_by=user)
                    task = self.task(case, task_status, assigned_user=user)
                    self.assertEqual(self.action(case, outcome=outcome).status_code, 200)
        expected = set(Case.objects.values_list("pk", flat=True))
        hidden = self.case(status=CaseStatus.COMPLETED)
        self.task(hidden)
        for state in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            self.task(self.case(created_by=user, status=CaseStatus.COMPLETED), state, assigned_user=user)
        self.case(created_by=user, status=CaseStatus.COMPLETED)
        archived = self.case(created_by=user, is_archived=True, status=CaseStatus.COMPLETED)
        self.task(archived, assigned_user=user)
        self.api.force_authenticate(user)
        self.client.force_login(user)
        for bucket in ("all", "overdue", "awaiting", "dormant", "edd_missing"):
            listed = self.api.get(reverse("api:case_list"), {"bucket": bucket})
            searched = self.api.post(reverse("api:case_search"), {"query": "Synthetic", "bucket": bucket}, format="json")
            wanted = expected if bucket in ("all", "overdue") else set()
            if bucket == "awaiting":
                wanted = set(Case.objects.filter(pk__in=expected, tasks__status=TaskStatus.AWAITING_REPORTS).values_list("pk", flat=True))
            for response in (listed, searched):
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual({row["id"] for row in response.data["results"]}, wanted)
                self.assertEqual(response.data["stats"]["overdue"], 4)
                self.assertEqual(response.data["stats"]["dormant"], 0)
            if bucket == "overdue":
                self.assertTrue(all(row["follow_up"]["label"] == "Overdue" for row in listed.data["results"]))
        response = self.client.get(reverse("patients:follow_up_list"), {"bucket": "overdue"})
        self.assertEqual({case.pk for group in response.context["patient_groups"] for case in group["cases"]}, expected)
