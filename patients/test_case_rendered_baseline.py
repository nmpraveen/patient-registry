"""Real browser GET/POST version and normalized ANC link regressions."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from api.views import _case_edit_payload
from . import test_follow_up
from .models import CaseDataScope, CaseStatus, DepartmentConfig, RoleSetting


class RenderedCaseBaselineTests(TestCase):
    client_class = test_follow_up.FollowUpTests.client_class
    setUp = test_follow_up.FollowUpTests.setUp
    case = test_follow_up.FollowUpTests.case
    action = test_follow_up.FollowUpTests.action

    def edit_page(self, case):
        url = reverse("patients:case_edit", args=[case.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="rendered_baseline"')
        data = {key: value if value is not None else "" for key, value in _case_edit_payload(case).items()}
        data["rendered_baseline"] = response.context["form"]["rendered_baseline"].value()
        return url, data

    def test_original_get_form_cannot_overwrite_later_outcome_or_edd_correction(self):
        other = get_user_model().objects.create_superuser("other-clinician")
        self.api.force_authenticate(other)
        for action in ("outcome", "correct_edd"):
            with self.subTest(action=action):
                case = self.case(prefix="MRS", age=25, gender="FEMALE")
                url, original_data = self.edit_page(case)
                original_data["notes"] = "Stale browser draft"
                response = self.action(case, action=action, usg_edd=(self.today + timedelta(days=12)).isoformat())
                self.assertEqual(response.status_code, 200, response.data)
                response = self.client.post(url, original_data)
                self.assertContains(response, "This case changed while you were editing. Reload before saving.")
                case.refresh_from_db()
                self.assertNotEqual(case.notes, "Stale browser draft")
                if action == "outcome":
                    self.assertEqual((case.status, case.anc_outcome), (CaseStatus.COMPLETED, "delivery"))
                    self.assertEqual(case.activity_logs.filter(note__startswith="ANC outcome:").count(), 1)
                else:
                    self.assertEqual(case.usg_edd, self.today + timedelta(days=12))
                    self.assertEqual(case.activity_logs.filter(note__startswith="USG EDD corrected:").count(), 1)

    def test_current_web_form_and_independent_api_patch_remain_valid(self):
        case = self.case(prefix="MRS", age=25, gender="FEMALE")
        url, data = self.edit_page(case)
        data["notes"] = "Current web draft"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.notes, "Current web draft")
        response = self.api.patch(reverse("api:case_detail", args=[case.pk]), {
            "notes": "Current API draft", "base_values": {"notes": case.notes},
            "base_updated_at": case.updated_at.isoformat(), "client_write_id": "independent-api-baseline"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        case.refresh_from_db()
        self.assertEqual(case.notes, "Current API draft")

    def test_missing_malformed_tampered_and_wrong_case_baselines_reject(self):
        case = self.case(prefix="MRS", age=25, gender="FEMALE")
        url, data = self.edit_page(case)
        _, other_data = self.edit_page(self.case(prefix="MRS", age=25, gender="FEMALE"))
        for baseline in (None, "invalid", data["rendered_baseline"] + "tampered", other_data["rendered_baseline"]):
            with self.subTest(baseline=baseline):
                submitted = dict(data, notes="Untrusted draft")
                if baseline is None:
                    submitted.pop("rendered_baseline")
                else:
                    submitted["rendered_baseline"] = baseline
                self.assertContains(self.client.post(url, submitted), "Reload before saving.")
                case.refresh_from_db()
                self.assertNotEqual(case.notes, "Untrusted draft")

    def test_baseline_is_bound_to_the_rendered_editor(self):
        case = self.case(prefix="MRS", age=25, gender="FEMALE")
        url, data = self.edit_page(case)
        other = get_user_model().objects.create_superuser("different-editor")
        self.client.force_login(other)
        self.assertContains(self.client.post(url, dict(data, notes="Different editor")), "Reload before saving.")
        case.refresh_from_db()
        self.assertNotEqual(case.notes, "Different editor")

    def test_mixed_case_anc_link_matches_workflow_and_permission(self):
        self.anc.name = "Anc"
        self.anc.save()
        case = self.case()
        url = reverse("patients:case_detail", args=[case.pk])
        action_url = reverse("patients:anc_action", args=[case.pk])
        self.assertContains(self.client.get(url), f'href="{action_url}"')
        self.assertEqual(self.client.get(action_url).status_code, 200)
        viewer = get_user_model().objects.create_user("anc-viewer")
        group = Group.objects.create(name="AncViewer")
        RoleSetting.objects.create(role_name=group.name, case_data_scope=CaseDataScope.ALL, can_case_edit=False)
        viewer.groups.add(group)
        self.client.force_login(viewer)
        self.assertNotContains(self.client.get(url), f'href="{action_url}"')
        self.assertEqual(self.client.get(action_url).status_code, 403)
