import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import DepartmentThemeForm, ThemeSettingsForm
from .models import (
    Case,
    CasePrefix,
    CaseStatus,
    DepartmentConfig,
    Gender,
    Patient,
    Task,
    TaskStatus,
    TaskType,
    ThemeSettings,
)
from .theme import flatten_theme_tokens, merge_theme_tokens


class FrontendAccessibilityRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="frontend-admin",
            password="frontend-test-password",
            email="frontend@example.test",
        )
        cls.department, _ = DepartmentConfig.objects.get_or_create(name="Medicine")
        cls.source_case = Case.objects.create(
            uhid="UH-A11Y-SOURCE",
            prefix=CasePrefix.MS,
            first_name="A11y",
            last_name="Source",
            gender=Gender.FEMALE,
            age=34,
            phone_number="9000000101",
            category=cls.department,
            status=CaseStatus.ACTIVE,
            diagnosis="Longitudinal follow-up",
            review_date=timezone.localdate() + timedelta(days=2),
            created_by=cls.admin,
        )
        cls.target_case = Case.objects.create(
            uhid="UH-A11Y-TARGET",
            prefix=CasePrefix.MR,
            first_name="A11y",
            last_name="Target",
            gender=Gender.MALE,
            age=36,
            phone_number="9000000102",
            category=cls.department,
            status=CaseStatus.ACTIVE,
            diagnosis="Target record",
            review_date=timezone.localdate() + timedelta(days=3),
            created_by=cls.admin,
        )
        Task.objects.create(
            case=cls.source_case,
            title="Follow-up call",
            due_date=timezone.localdate() + timedelta(days=1),
            status=TaskStatus.SCHEDULED,
            task_type=TaskType.CALL,
            created_by=cls.admin,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_authenticated_pages_have_private_no_store_and_nonce_csp(self):
        response = self.client.get(reverse("patients:patient_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store, max-age=0")
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertEqual(response.headers["Expires"], "0")
        self.assertIn("Cookie", response.headers["Vary"])
        self.assertIn("Authorization", response.headers["Vary"])
        self.assertEqual(response.headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(response.headers["X-Permitted-Cross-Domain-Policies"], "none")
        self.assertIn("camera=()", response.headers["Permissions-Policy"])

        html = response.content.decode()
        nonce_match = re.search(r'<script nonce="([^"]+)"', html)
        self.assertIsNotNone(nonce_match)
        nonce = nonce_match.group(1)
        csp = response.headers["Content-Security-Policy"]
        self.assertIn(f"script-src 'self' blob: 'nonce-{nonce}'", csp)
        self.assertIn(f"style-src-elem 'self' 'nonce-{nonce}'", csp)
        self.assertIn("script-src-attr 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("cdn.jsdelivr.net", csp)
        self.assertNotIn("fonts.googleapis.com", csp)

    def test_base_template_uses_local_pinned_assets_skip_link_and_combobox_semantics(self):
        response = self.client.get(reverse("patients:dashboard"))
        html = response.content.decode()

        for external_host in (
            "cdn.jsdelivr.net",
            "fonts.googleapis.com",
            "fonts.gstatic.com",
            "unpkg.com",
        ):
            self.assertNotIn(external_host, html)
        self.assertIn("/static/patients/vendor/bootstrap/5.3.3/", html)
        self.assertIn("/static/patients/vendor/crayons/4.1.0/", html)
        self.assertIn('class="skip-link" href="#main-content"', html)
        self.assertRegex(html, r'<main[^>]+id="main-content"[^>]+tabindex="-1"')
        self.assertIn('role="combobox"', html)
        self.assertIn('aria-autocomplete="list"', html)
        self.assertIn('aria-controls="global-search-dropdown"', html)
        self.assertIn('role="listbox"', html)
        self.assertIn('id="global-search-status"', html)
        self.assertIn('role="status"', html)

    def test_templates_have_nonce_capable_inline_blocks_and_no_inline_handlers(self):
        templates_dir = Path(settings.BASE_DIR) / "templates"
        for template_path in templates_dir.rglob("*.html"):
            template = template_path.read_text(encoding="utf-8")
            for match in re.finditer(r"<script(?![^>]*\bsrc=)([^>]*)>", template, re.IGNORECASE):
                self.assertIn("nonce=", match.group(1), template_path.as_posix())
            for match in re.finditer(r"<style([^>]*)>", template, re.IGNORECASE):
                self.assertIn("nonce=", match.group(1), template_path.as_posix())
            self.assertIsNone(
                re.search(r"\son(?:click|change|input|submit|load|error)=", template, re.IGNORECASE),
                template_path.as_posix(),
            )

    def test_user_and_role_forms_have_unique_prefixed_dom_ids(self):
        users_response = self.client.get(reverse("patients:settings_user_management"), {"tab": "users"})
        roles_response = self.client.get(reverse("patients:settings_user_management"), {"tab": "roles"})
        html = users_response.content.decode() + roles_response.content.decode()

        expected_ids = {
            "id_user-create-first_name",
            "id_user-edit-first_name",
            "id_role-create-role_name",
            "id_role-edit-role_name",
        }
        for expected_id in expected_ids:
            self.assertIn(f'id="{expected_id}"', html)

        for response in (users_response, roles_response):
            page_html = response.content.decode()
            ids = re.findall(r'id="(id_(?:user|role)-(?:create|edit)-[^"]+)"', page_html)
            self.assertEqual(len(ids), len(set(ids)))

    def test_search_filter_and_call_selection_controls_have_accessible_labels(self):
        patient_response = self.client.get(reverse("patients:patient_list"))
        case_response = self.client.get(reverse("patients:case_list"))
        users_response = self.client.get(reverse("patients:settings_user_management"))
        calls_response = self.client.get(reverse("patients:calls_upcoming"))

        self.assertContains(patient_response, 'for="patient-list-search"')
        for control_id in (
            "case-list-search",
            "case-filter-status",
            "case-filter-category",
            "case-filter-subcategory",
            "case-filter-due-start",
            "case-filter-due-end",
        ):
            self.assertContains(case_response, f'for="{control_id}"')
        self.assertContains(users_response, 'for="user-management-search"')
        self.assertContains(calls_response, f'for="call-case-{self.source_case.pk}"')
        self.assertContains(calls_response, "UHID UH-A11Y-SOURCE")
        self.assertContains(calls_response, 'role="status" aria-live="polite"')

    def test_patient_merge_requires_review_target_uhid_and_confirmation(self):
        detail_url = reverse("patients:patient_detail", kwargs={"pk": self.source_case.patient_id})
        merge_url = reverse("patients:patient_merge", kwargs={"pk": self.source_case.patient_id})

        review = self.client.get(detail_url, {"target_patient": self.target_case.patient_id})
        self.assertEqual(review.status_code, 200)
        self.assertContains(review, "Review Patient Merge")
        self.assertContains(review, self.source_case.patient.uhid)
        self.assertContains(review, self.target_case.patient.uhid)
        self.assertContains(review, f"Case #{self.source_case.pk}")
        self.assertContains(review, "Type target UHID to confirm")

        rejected = self.client.post(
            merge_url,
            {
                "target_patient": self.target_case.patient_id,
                "confirm_target_uhid": "WRONG-UHID",
                "confirm_merge": "on",
            },
        )
        self.assertEqual(rejected.status_code, 302)
        self.source_case.refresh_from_db()
        self.assertNotEqual(self.source_case.patient_id, self.target_case.patient_id)

        source_patient_id = self.source_case.patient_id
        accepted = self.client.post(
            merge_url,
            {
                "target_patient": self.target_case.patient_id,
                "confirm_target_uhid": self.target_case.patient.uhid,
                "confirm_merge": "on",
            },
        )
        self.assertEqual(accepted.status_code, 302)
        self.source_case.refresh_from_db()
        self.assertEqual(self.source_case.patient_id, self.target_case.patient_id)
        self.assertEqual(Patient.objects.get(pk=source_patient_id).merged_into_id, self.target_case.patient_id)

    def test_theme_contrast_validation_rejects_invalid_pairs_and_preview_is_visible(self):
        theme_settings = ThemeSettings.get_solo()
        form_data = flatten_theme_tokens(merge_theme_tokens(theme_settings.tokens))
        self.assertTrue(ThemeSettingsForm(form_data, instance=theme_settings).is_valid())
        form_data["shell__page_text"] = form_data["shell__page_bg"]
        form = ThemeSettingsForm(form_data, instance=theme_settings)

        self.assertFalse(form.is_valid())
        self.assertIn("contrast", " ".join(form.errors["shell__page_text"]).lower())

        department_form = DepartmentThemeForm(
            {"theme_bg_color": "#ffffff", "theme_text_color": "#ffffff"},
            instance=self.department,
        )
        self.assertFalse(department_form.is_valid())
        self.assertIn("contrast", " ".join(department_form.errors["theme_text_color"]).lower())

        response = self.client.get(reverse("patients:settings_theme"))
        self.assertContains(response, "data-contrast-summary")
        self.assertContains(response, "data-theme-save")

    def test_case_detail_feedback_uses_text_nodes_and_responsive_guards_exist(self):
        static_dir = Path(settings.BASE_DIR) / "patients" / "static" / "patients"
        script = (static_dir / "case_detail.js").read_text(encoding="utf-8")
        stylesheet = (static_dir / "case_detail.css").read_text(encoding="utf-8")
        patient_template = (Path(settings.BASE_DIR) / "templates" / "patients" / "patient_detail.html").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("feedback.innerHTML", script)
        self.assertIn("feedback.replaceChildren", script)
        self.assertIn("messageLine.textContent", script)
        self.assertIn("max-width: 100%", stylesheet)
        self.assertIn("overflow-x: clip", stylesheet)
        self.assertIn("merge_form.target_patient", patient_template)


class ThirdPartyAssetPinningTests(TestCase):
    def test_expected_vendor_assets_and_licenses_are_present(self):
        vendor = Path(settings.BASE_DIR) / "patients" / "static" / "patients" / "vendor"
        expected = (
            "bootstrap/5.3.3/bootstrap.min.css",
            "bootstrap/5.3.3/bootstrap.bundle.min.js",
            "bootstrap/5.3.3/LICENSE",
            "crayons/4.1.0/crayons-min.css",
            "crayons/4.1.0/dist/crayons/crayons.esm.js",
            "crayons/4.1.0/LICENSE.md",
            "htmx/1.9.12/htmx.min.js",
            "htmx/1.9.12/LICENSE",
            "chartjs/4.4.4/chart.umd.js",
            "chartjs/4.4.4/LICENSE.md",
            "inter/5.2.8/inter.css",
            "inter/5.2.8/LICENSE",
            "crayons-icons/4.2.0-beta.0/LICENSE.md",
        )
        for relative_path in expected:
            self.assertTrue((vendor / relative_path).is_file(), relative_path)
