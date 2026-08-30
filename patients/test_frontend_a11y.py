import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from scripts.verify_web_vendor_integrity import verify_manifest

from .forms import DepartmentThemeForm, ThemeSettingsForm
from .models import (
    Case,
    CaseDataScope,
    CasePrefix,
    CaseStatus,
    DepartmentConfig,
    Gender,
    Patient,
    RoleSetting,
    Task,
    TaskStatus,
    TaskType,
    ThemeSettings,
)
from .theme import (
    CATEGORY_THEME_DEFAULTS,
    NEUTRAL_CATEGORY_THEME,
    PAIR_GROUPS,
    THEME_CONTRAST_RULES,
    THEME_DERIVED_TEXT_CONTRAST_RULES,
    THEME_DEFAULTS,
    THEME_FOCUS_CONTRAST_RULES,
    contrast_safe_hover_color,
    contrast_ratio,
    flatten_theme_tokens,
    merge_theme_tokens,
    theme_field_definitions,
)


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

    def assert_private_no_store(self, response):
        self.assertEqual(response.headers["Cache-Control"], "private, no-store, max-age=0")
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertEqual(response.headers["Expires"], "0")
        self.assertIn("Cookie", response.headers["Vary"])
        self.assertIn("Authorization", response.headers["Vary"])

    def test_authenticated_pages_have_private_no_store_and_nonce_csp(self):
        response = self.client.get(reverse("patients:patient_list"))

        self.assertEqual(response.status_code, 200)
        self.assert_private_no_store(response)
        self.assertEqual(response.headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(response.headers["X-Permitted-Cross-Domain-Policies"], "none")
        self.assertIn("camera=()", response.headers["Permissions-Policy"])

        html = response.content.decode()
        nonce_match = re.search(r'<script nonce="([^"]+)"', html)
        self.assertIsNotNone(nonce_match)
        nonce = nonce_match.group(1)
        csp = response.headers["Content-Security-Policy"]
        self.assertIn(f"script-src 'self' 'nonce-{nonce}'", csp)
        self.assertNotIn("script-src 'self' blob:", csp)
        self.assertIn(f"style-src-elem 'self' 'nonce-{nonce}'", csp)
        self.assertIn("script-src-attr 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("cdn.jsdelivr.net", csp)
        self.assertNotIn("fonts.googleapis.com", csp)

    def test_anonymous_auth_device_and_phi_responses_are_private_no_store(self):
        anonymous = Client()

        token_response = anonymous.post(
            reverse("api:token_obtain_pair"),
            {"username": self.admin.username, "password": "frontend-test-password"},
        )
        self.assertEqual(token_response.status_code, 200)
        self.assertIn("access", token_response.json())
        self.assertIn("refresh", token_response.json())
        self.assert_private_no_store(token_response)

        refresh_response = anonymous.post(
            reverse("api:token_refresh"),
            {"refresh": token_response.json()["refresh"]},
        )
        self.assertEqual(refresh_response.status_code, 200)
        self.assert_private_no_store(refresh_response)

        invalid_token_response = anonymous.post(
            reverse("api:token_obtain_pair"),
            {"username": self.admin.username, "password": "wrong-password"},
        )
        self.assertEqual(invalid_token_response.status_code, 401)
        self.assert_private_no_store(invalid_token_response)

        session = anonymous.session
        session["device_access_pending_login"] = {
            "user_id": self.admin.pk,
            "backend": "django.contrib.auth.backends.ModelBackend",
            "redirect_to": reverse("patients:dashboard"),
        }
        session.save()
        pending_page = anonymous.get(reverse("login_device_verification"))
        self.assertEqual(pending_page.status_code, 200)
        self.assert_private_no_store(pending_page)

        pending_error = anonymous.post(
            reverse("login_device_register_verify"),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(pending_error.status_code, 403)
        self.assert_private_no_store(pending_error)

        phi_redirect = Client().get(reverse("patients:patient_list"))
        self.assertEqual(phi_redirect.status_code, 302)
        self.assert_private_no_store(phi_redirect)

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
        self.assertIn("crayons-csp-loader.js", html)
        self.assertIn('class="skip-link" href="#main-content"', html)
        self.assertRegex(html, r'<main[^>]+id="main-content"[^>]+tabindex="-1"')
        self.assertIn('role="combobox"', html)
        self.assertIn('aria-autocomplete="list"', html)
        self.assertIn('aria-controls="global-search-dropdown"', html)
        self.assertIn('role="listbox"', html)
        self.assertIn('id="global-search-status"', html)
        self.assertIn('role="status"', html)

        loader_path = (
            Path(settings.BASE_DIR)
            / "patients/static/patients/vendor/crayons/4.1.0/dist/crayons/crayons-csp-loader.js"
        )
        loader = loader_path.read_text(encoding="utf-8")
        self.assertIn('import("./crayons.esm.js")', loader)
        self.assertNotIn("new Blob", loader)
        self.assertNotIn("createObjectURL", loader)

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
        self.assertContains(review, f"Case #{self.target_case.pk}")
        self.assertContains(review, "Source - will move")
        self.assertContains(review, "Target - remains")
        self.assertContains(review, "Complete affected set")
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

    def test_patient_merge_blocks_when_any_target_case_is_inaccessible(self):
        restricted_user = get_user_model().objects.create_user(
            username="restricted-merger",
            password="restricted-password",
        )
        role_name = "Restricted Merge Reviewer"
        RoleSetting.objects.create(
            role_name=role_name,
            case_data_scope=CaseDataScope.ASSIGNED,
            can_patient_merge=True,
        )
        group = Group.objects.create(name=role_name)
        restricted_user.groups.add(group)

        source_case = Case.objects.create(
            uhid="UH-RESTRICTED-SOURCE",
            prefix=CasePrefix.MS,
            first_name="Restricted",
            last_name="Source",
            gender=Gender.FEMALE,
            age=31,
            phone_number="9000000111",
            category=self.department,
            status=CaseStatus.ACTIVE,
            diagnosis="Accessible source",
            created_by=restricted_user,
        )
        target_case = Case.objects.create(
            uhid="UH-RESTRICTED-TARGET",
            prefix=CasePrefix.MR,
            first_name="Restricted",
            last_name="Target",
            gender=Gender.MALE,
            age=32,
            phone_number="9000000112",
            category=self.department,
            status=CaseStatus.ACTIVE,
            diagnosis="Accessible target case",
            created_by=restricted_user,
        )
        inaccessible_target_case = Case.objects.create(
            patient=target_case.patient,
            uhid=target_case.uhid,
            prefix=target_case.prefix,
            first_name=target_case.first_name,
            last_name=target_case.last_name,
            gender=target_case.gender,
            age=target_case.age,
            phone_number=target_case.phone_number,
            category=self.department,
            status=CaseStatus.ACTIVE,
            diagnosis="Inaccessible target case",
            created_by=self.admin,
        )

        restricted_client = Client()
        restricted_client.force_login(restricted_user)
        detail_url = reverse("patients:patient_detail", kwargs={"pk": source_case.patient_id})
        review = restricted_client.get(detail_url, {"target_patient": target_case.patient_id})
        self.assertEqual(review.status_code, 200)
        self.assertContains(review, "Review blocked: you need access to every case attached to both the source and target patient.")
        self.assertNotContains(review, "Confirm Merge")
        self.assertNotContains(review, f"Case #{inaccessible_target_case.pk}")

        merge_response = restricted_client.post(
            reverse("patients:patient_merge", kwargs={"pk": source_case.patient_id}),
            {
                "target_patient": target_case.patient_id,
                "confirm_target_uhid": target_case.patient.uhid,
                "confirm_merge": "on",
            },
        )
        self.assertEqual(merge_response.status_code, 403)
        source_case.refresh_from_db()
        self.assertNotEqual(source_case.patient_id, target_case.patient_id)

    def test_theme_contrast_validation_rejects_invalid_pairs_and_preview_is_visible(self):
        theme_settings = ThemeSettings.get_solo()
        form_data = flatten_theme_tokens(merge_theme_tokens(theme_settings.tokens))
        self.assertTrue(ThemeSettingsForm(form_data, instance=theme_settings).is_valid())

        editable_fields = set(theme_field_definitions())
        editable_text_pairs = {
            (field_name, field_name.removesuffix("__text") + "__bg")
            for field_name in editable_fields
            if field_name.endswith("__text") and field_name.removesuffix("__text") + "__bg" in editable_fields
        }
        text_rule_pairs = {(text_field, background_field) for text_field, background_field, _, _ in THEME_CONTRAST_RULES}
        self.assertLessEqual(editable_text_pairs, text_rule_pairs)
        outline_text_fields = {field_name for field_name in editable_fields if field_name.endswith("__outline_text")}
        self.assertEqual(
            outline_text_fields,
            {text_field for text_field, _, _, _ in THEME_CONTRAST_RULES if text_field.endswith("__outline_text")},
        )
        self.assertTrue(all(minimum_ratio == 4.5 for _, _, minimum_ratio, _ in THEME_CONTRAST_RULES))

        def default_color(field_name):
            value = THEME_DEFAULTS
            for key in field_name.split("__"):
                value = value[key]
            return value

        for text_field, background_field, minimum_ratio, label in THEME_CONTRAST_RULES:
            with self.subTest(text_pair=label):
                self.assertGreaterEqual(
                    contrast_ratio(default_color(text_field), default_color(background_field)),
                    minimum_ratio,
                )
                invalid_data = dict(form_data)
                invalid_data[text_field] = invalid_data[background_field]
                invalid_form = ThemeSettingsForm(invalid_data, instance=theme_settings)
                self.assertFalse(invalid_form.is_valid())
                self.assertIn("minimum 4.5:1", " ".join(invalid_form.errors[text_field]))

        derived_rule_pairs = {
            (text_field, background_field)
            for text_field, background_field, _, minimum_ratio, _ in THEME_DERIVED_TEXT_CONTRAST_RULES
            if minimum_ratio == 4.5
        }
        self.assertEqual(
            {
                (f"{section_name}__{token_name}__text", f"{section_name}__{token_name}__bg")
                for section_name, token_name in PAIR_GROUPS
            },
            derived_rule_pairs,
        )
        for text_field, background_field, mix_ratio, minimum_ratio, label in THEME_DERIVED_TEXT_CONTRAST_RULES:
            with self.subTest(derived_pair=label):
                interaction_background = contrast_safe_hover_color(
                    default_color(background_field),
                    default_color(text_field),
                    mix_ratio,
                )
                self.assertGreaterEqual(
                    contrast_ratio(default_color(text_field), interaction_background),
                    minimum_ratio,
                )

        self.assertTrue(all(minimum_ratio == 3.0 for _, _, minimum_ratio, _ in THEME_FOCUS_CONTRAST_RULES))
        for indicator_field, background_field, minimum_ratio, label in THEME_FOCUS_CONTRAST_RULES:
            with self.subTest(focus_pair=label):
                self.assertGreaterEqual(
                    contrast_ratio(default_color(indicator_field), default_color(background_field)),
                    minimum_ratio,
                )

        focus_boundary_data = dict(form_data)
        focus_boundary_data.update(
            {
                "shell__page_bg": "#ffffff",
                "shell__surface_bg": "#ffffff",
                "nav__bg": "#ffffff",
                "shell__focus_indicator": "#949494",
            }
        )
        self.assertTrue(ThemeSettingsForm(focus_boundary_data, instance=theme_settings).is_valid())
        focus_boundary_data["shell__focus_indicator"] = "#959595"
        focus_form = ThemeSettingsForm(focus_boundary_data, instance=theme_settings)
        self.assertFalse(focus_form.is_valid())
        self.assertIn("minimum 3.0:1", " ".join(focus_form.errors["shell__focus_indicator"]))

        for name, colors in (*CATEGORY_THEME_DEFAULTS.items(), ("Neutral", NEUTRAL_CATEGORY_THEME)):
            with self.subTest(category=name):
                self.assertGreaterEqual(contrast_ratio(colors["text"], colors["bg"]), 4.5)
                self.assertGreaterEqual(
                    contrast_ratio(
                        colors["text"],
                        contrast_safe_hover_color(colors["bg"], colors["text"], 0.10),
                    ),
                    4.5,
                )

        department_form = DepartmentThemeForm(
            {"theme_bg_color": "#ffffff", "theme_text_color": "#ffffff"},
            instance=self.department,
        )
        self.assertFalse(department_form.is_valid())
        self.assertIn("contrast", " ".join(department_form.errors["theme_text_color"]).lower())

        response = self.client.get(reverse("patients:settings_theme"))
        self.assertContains(response, "data-contrast-summary")
        self.assertContains(response, "data-theme-save")
        self.assertContains(response, "const textContrastRules")
        self.assertContains(response, "const derivedTextContrastRules")
        self.assertContains(response, "const focusContrastRules")
        self.assertContains(response, "shell__focus_indicator")

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
    def test_vendor_tree_matches_reviewed_integrity_manifest(self):
        self.assertEqual(verify_manifest(), [])
        vendor = Path(settings.BASE_DIR) / "patients" / "static" / "patients" / "vendor"
        manifest = json.loads((Path(settings.BASE_DIR) / "WEB_VENDOR_INTEGRITY.json").read_text(encoding="utf-8"))
        expected = manifest["files"]
        actual_paths = {
            path.relative_to(vendor).as_posix(): path
            for path in vendor.rglob("*")
            if path.is_file()
        }
        self.assertEqual(set(actual_paths), set(expected))
        for relative_path, path in actual_paths.items():
            with self.subTest(vendor_file=relative_path):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected[relative_path])
        for package in manifest["packages"]:
            self.assertTrue((vendor / package["license_file"]).is_file(), package["name"])
            self.assertTrue(package["archive_integrity"].startswith("sha512-"), package["name"])

    def test_expected_vendor_assets_and_licenses_are_present(self):
        vendor = Path(settings.BASE_DIR) / "patients" / "static" / "patients" / "vendor"
        expected = (
            "bootstrap/5.3.3/bootstrap.min.css",
            "bootstrap/5.3.3/bootstrap.bundle.min.js",
            "bootstrap/5.3.3/LICENSE",
            "crayons/4.1.0/crayons-min.css",
            "crayons/4.1.0/dist/crayons/crayons-csp-loader.js",
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
