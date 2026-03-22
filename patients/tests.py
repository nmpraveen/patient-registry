import io
import re
from copy import deepcopy
import hashlib
import json
import tempfile
import zipfile
from datetime import datetime, time as dt_time, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import ProgrammingError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .forms import CaseForm, DepartmentThemeForm
from . import database_bundle
from . import backup_scheduler
from .models import (
    ActivityEventType,
    AncHighRiskReason,
    CallCommunicationStatus,
    CallLog,
    CallOutcome,
    Case,
    CaseActivityLog,
    CasePrefix,
    CaseSubcategory,
    CaseStatus,
    DepartmentConfig,
    DeviceApprovalPolicy,
    DEVICE_APPROVAL_MAX_APPROVED,
    default_case_subcategory_for_category_name,
    Gender,
    NonCommunicableDisease,
    PatientDataBackupSchedule,
    PatientDataBackupStatus,
    PatientDataBackupTrigger,
    QUICK_ENTRY_DETAILS_TASK_TITLE,
    RCH_REMINDER_INTERVAL_DAYS,
    RCH_REMINDER_TASK_TITLE,
    RoleSetting,
    STAFF_PILOT_ROLE_NAME,
    STAFF_ROLE_NAME,
    StaffDeviceCredential,
    StaffDeviceCredentialStatus,
    SurgicalPathway,
    Task,
    TaskType,
    TaskStatus,
    ThemeSettings,
    UserAdminNote,
    VitalEntry,
    build_default_tasks,
    ensure_default_departments,
    ensure_default_role_settings,
    plan_default_tasks,
)
from .theme import (
    field_name_to_css_var,
    flatten_theme_tokens,
    merge_theme_tokens,
    mix_colors,
    normalize_hex_color,
    rgba_string,
)


class MedtrackModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="doctor", password="pw12345")
        self.anc, _ = DepartmentConfig.objects.get_or_create(name="ANC", defaults={"predefined_actions": ["USG"], "metadata_template": {"lmp": "date"}})
        self.surgery, _ = DepartmentConfig.objects.get_or_create(name="Surgery", defaults={"predefined_actions": ["LAB TEST"], "metadata_template": {"surgical_pathway": "String"}})
        self.medicine, _ = DepartmentConfig.objects.get_or_create(name="Medicine", defaults={"predefined_actions": ["Consultant Review"], "metadata_template": {"review_date": "Date"}})

    def test_case_save_normalizes_patient_names_and_place(self):
        case = Case.objects.create(
            uhid="UH-NAME-001",
            prefix=CasePrefix.MRS,
            first_name="  FIRST   NAME  ",
            last_name="  lAST   NAME  ",
            place="  cHENNAI  ",
            phone_number="9000000001",
            category=self.anc,
            lmp=timezone.localdate() - timedelta(days=70),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )

        self.assertEqual(case.first_name, "First Name")
        self.assertEqual(case.last_name, "Last Name")
        self.assertEqual(case.place, "Chennai")
        self.assertEqual(case.patient_name, "Mrs. First Name Last Name")

    def test_case_save_with_update_fields_normalizes_names_place_and_keeps_patient_name_synced(self):
        case = Case.objects.create(
            uhid="UH-NAME-002",
            prefix=CasePrefix.MS,
            first_name="Asha",
            last_name="Devi",
            place="Pune",
            phone_number="9000000002",
            category=self.anc,
            lmp=timezone.localdate() - timedelta(days=70),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )

        case.prefix = CasePrefix.MRS
        case.first_name = "  FIRST   NAME  "
        case.place = "  nEW   dELHI  "
        case.save(update_fields=["prefix", "first_name", "place"])
        case.refresh_from_db()

        self.assertEqual(case.prefix, CasePrefix.MRS)
        self.assertEqual(case.first_name, "First Name")
        self.assertEqual(case.last_name, "Devi")
        self.assertEqual(case.place, "New Delhi")
        self.assertEqual(case.patient_name, "Mrs. First Name Devi")

    def test_case_save_with_unrelated_update_fields_does_not_rewrite_names(self):
        case = Case.objects.create(
            uhid="UH-NAME-003",
            first_name="Asha",
            last_name="Devi",
            phone_number="9000000003",
            category=self.anc,
            lmp=timezone.localdate() - timedelta(days=70),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )
        Case.objects.filter(pk=case.pk).update(
            first_name="  FIRST   NAME  ",
            last_name="  mR  ",
            patient_name="  FIRST   NAME     mR  ",
        )

        case.refresh_from_db()
        case.notes = "Updated note"
        case.save(update_fields=["notes"])
        case.refresh_from_db()

        self.assertEqual(case.first_name, "  FIRST   NAME  ")
        self.assertEqual(case.last_name, "  mR  ")
        self.assertEqual(case.patient_name, "  FIRST   NAME     mR  ")

    def test_plan_default_tasks_for_anc_returns_preview_without_writing_tasks(self):
        preview_case = Case(
            uhid="UH-PLAN-ANC",
            first_name="Preview",
            last_name="ANC",
            phone_number="9000000004",
            category=self.anc,
            lmp=timezone.localdate() - timedelta(days=56),
            edd=timezone.localdate() + timedelta(days=210),
        )

        task_plan = plan_default_tasks(preview_case)

        self.assertGreaterEqual(len(task_plan), 20)
        self.assertEqual(task_plan[0]["title"], "Routine prenatal check up")
        self.assertFalse(Task.objects.exists())

    def test_plan_default_tasks_matches_persisted_planned_surgery_tasks(self):
        preview_case = Case(
            uhid="UH-PLAN-SURG",
            first_name="Preview",
            last_name="Surgery",
            phone_number="9000000005",
            category=self.surgery,
            surgical_pathway=SurgicalPathway.PLANNED_SURGERY,
            surgery_date=timezone.localdate() + timedelta(days=7),
        )

        task_plan = plan_default_tasks(preview_case)
        persisted_case = Case.objects.create(
            uhid="UH-PLAN-SURG",
            first_name="Preview",
            last_name="Surgery",
            phone_number="9000000005",
            category=self.surgery,
            surgical_pathway=SurgicalPathway.PLANNED_SURGERY,
            surgery_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        created_tasks = build_default_tasks(persisted_case, self.user)

        self.assertEqual(
            [(item["title"], item["due_date"], item["task_type"], item["frequency_label"]) for item in task_plan],
            [(task.title, task.due_date, task.task_type, task.frequency_label) for task in created_tasks],
        )

    def test_plan_default_tasks_for_medicine_uses_first_predefined_action(self):
        preview_case = Case(
            uhid="UH-PLAN-MED",
            first_name="Preview",
            last_name="Medicine",
            phone_number="9000000006",
            category=self.medicine,
            review_frequency="MONTHLY",
            review_date=timezone.localdate() + timedelta(days=14),
        )

        task_plan = plan_default_tasks(preview_case)

        self.assertEqual(len(task_plan), 1)
        self.assertEqual(task_plan[0]["title"], "Consultant Review")
        self.assertEqual(task_plan[0]["task_type"], TaskType.CUSTOM)

    def test_anc_case_requires_lmp_edd(self):
        case = Case(
            uhid="UH001",
            first_name="Jane",
            last_name="Doe",
            phone_number="9999999999",
            category=self.anc,
            created_by=self.user,
        )
        with self.assertRaises(Exception):
            case.full_clean()


    def test_anc_gpla_validation_blocks_invalid_values(self):
        case = Case(
            uhid="UH-GPLA",
            first_name="GPLA",
            last_name="Invalid",
            phone_number="9999999998",
            category=self.anc,
            lmp=timezone.localdate() - timedelta(days=56),
            edd=timezone.localdate() + timedelta(days=210),
            gravida=1,
            para=2,
            abortions=0,
            living=0,
            created_by=self.user,
        )
        with self.assertRaises(Exception):
            case.full_clean()

    def test_surgery_case_requires_subcategory_during_full_validation(self):
        case = Case(
            uhid="UH-SUBCAT-SURG-001",
            first_name="Surgery",
            last_name="Missing",
            phone_number="9999999997",
            category=self.surgery,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )

        with self.assertRaises(ValidationError) as exc:
            case.full_clean()

        self.assertIn("subcategory", exc.exception.message_dict)

    def test_medicine_case_rejects_mismatched_subcategory_during_full_validation(self):
        case = Case(
            uhid="UH-SUBCAT-MED-001",
            first_name="Medicine",
            last_name="Mismatch",
            phone_number="9999999996",
            category=self.medicine,
            subcategory=CaseSubcategory.GENERAL_SURGERY,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        with self.assertRaises(ValidationError) as exc:
            case.full_clean()

        self.assertIn("subcategory", exc.exception.message_dict)

    def test_non_surgery_categories_clear_subcategory_during_full_validation(self):
        case = Case(
            uhid="UH-SUBCAT-ANC-001",
            first_name="Anc",
            last_name="Cleared",
            phone_number="9999999995",
            category=self.anc,
            subcategory=CaseSubcategory.GENERAL_SURGERY,
            lmp=timezone.localdate() - timedelta(days=56),
            edd=timezone.localdate() + timedelta(days=210),
            rch_bypass=True,
            created_by=self.user,
        )

        case.full_clean()

        self.assertEqual(case.subcategory, "")

    def test_task_completion_sets_completed_at(self):
        case = Case.objects.create(
            uhid="UH100",
            first_name="A",
            last_name="One",
            phone_number="9999999999",
            category=self.anc,
            lmp=timezone.localdate() - timedelta(days=70),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )
        task = Task.objects.create(case=case, title="Lab", due_date=timezone.localdate(), created_by=self.user)
        self.assertIsNone(task.completed_at)
        task.status = TaskStatus.COMPLETED
        task.save()
        self.assertIsNotNone(task.completed_at)

    def test_task_string_representation_uses_title(self):
        case = Case.objects.create(
            uhid="UH101",
            first_name="B",
            last_name="Two",
            phone_number="9999999998",
            category=self.anc,
            lmp=timezone.localdate() - timedelta(days=70),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )
        task = Task.objects.create(case=case, title="ECG", due_date=timezone.localdate(), created_by=self.user)

        self.assertEqual(str(task), "ECG")

    def test_case_activity_log_defaults_to_system_event_type(self):
        case = Case.objects.create(
            uhid="UH-ACT-001",
            first_name="Activity",
            last_name="Default",
            phone_number="9000000000",
            category=self.anc,
            lmp=timezone.localdate() - timedelta(days=70),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )
        activity = CaseActivityLog.objects.create(case=case, user=self.user, note="System activity")

        self.assertEqual(activity.event_type, ActivityEventType.SYSTEM)

    def test_project_timezone_is_asia_kolkata(self):
        self.assertEqual(settings.TIME_ZONE, "Asia/Kolkata")


class ThemeSystemTests(TestCase):
    def test_normalize_hex_color_and_merge_theme_tokens_compute_derived_values(self):
        self.assertEqual(normalize_hex_color("#ABCDEF"), "#abcdef")
        with self.assertRaises(ValueError):
            normalize_hex_color("blue")
        self.assertEqual(field_name_to_css_var("shell__page_bg"), "--theme-shell-page-bg")
        self.assertEqual(field_name_to_css_var("case_header__bg"), "--theme-case-header-bg")
        self.assertEqual(
            field_name_to_css_var("case_status__loss_to_follow_up__bg"),
            "--theme-case-status-loss-to-follow-up-bg",
        )

        merged = merge_theme_tokens(
            {
                "buttons": {"primary": {"bg": "#112233", "text": "#ffffff"}},
                "vitals_chart": {"blood_pressure": "#112233"},
            }
        )

        self.assertEqual(merged["buttons"]["primary"]["border"], mix_colors("#112233", "#ffffff", 0.20))
        self.assertEqual(merged["buttons"]["primary"]["hover_bg"], mix_colors("#112233", "#ffffff", 0.10))
        self.assertEqual(merged["buttons"]["success"]["bg"], "#80cbc4")
        self.assertEqual(merged["vitals_chart"]["blood_pressure_fill"], rgba_string("#112233", 0.18))

    def test_merge_theme_tokens_maps_legacy_bp_chart_tokens_to_blood_pressure(self):
        merged = merge_theme_tokens(
            {
                "vitals_chart": {
                    "bp_systolic": "#112233",
                    "bp_diastolic": "#445566",
                }
            }
        )

        self.assertEqual(merged["vitals_chart"]["blood_pressure"], "#112233")
        self.assertEqual(merged["vitals_chart"]["blood_pressure_fill"], rgba_string("#112233", 0.18))
        self.assertNotIn("bp_systolic", merged["vitals_chart"])
        self.assertNotIn("bp_diastolic", merged["vitals_chart"])

    def test_theme_settings_singleton_normalizes_tokens_on_save(self):
        theme = ThemeSettings(tokens={"shell": {"page_bg": "#ABCDEF"}})
        theme.save()

        solo = ThemeSettings.get_solo()

        self.assertEqual(solo.pk, 1)
        self.assertEqual(solo.tokens["shell"]["page_bg"], "#abcdef")
        self.assertIn("nav", solo.tokens)
        self.assertIn("case_header", solo.tokens)
        self.assertEqual(ThemeSettings.objects.count(), 1)

    def test_department_config_theme_defaults_follow_category_name(self):
        anc = DepartmentConfig.objects.get(name="ANC")
        custom = DepartmentConfig.objects.create(name="Custom Clinic")

        self.assertEqual(anc.theme_bg_color, "#ffe0b2")
        self.assertEqual(anc.theme_text_color, "#bf360c")
        self.assertEqual(custom.theme_bg_color, "#e2e3e5")
        self.assertEqual(custom.theme_text_color, "#41464b")

    def test_department_theme_form_points_inputs_to_preview_chip_id(self):
        category = DepartmentConfig.objects.get(name="ANC")

        form = DepartmentThemeForm(instance=category)

        self.assertEqual(
            form.fields["theme_bg_color"].widget.attrs["data-category-preview"],
            f"theme-category-{category.pk}-preview",
        )


class MedtrackViewTests(TestCase):
    def setUp(self):
        ensure_default_role_settings()
        self.user = get_user_model().objects.create_user(username="doc", password="strong-password-123")
        doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        self.user.groups.add(doctor_group)

        self.anc, _ = DepartmentConfig.objects.get_or_create(name="ANC")
        self.surgery, _ = DepartmentConfig.objects.get_or_create(name="Surgery")
        self.medicine, _ = DepartmentConfig.objects.get_or_create(name="Medicine")
        self.case_sequence = 0

    def assert_max_queries(self, max_queries, url, params=None):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(url, params or {})
            self.assertEqual(response.status_code, 200)
            response.render()
        self.assertLessEqual(
            len(captured),
            max_queries,
            f"Expected at most {max_queries} queries, but saw {len(captured)}.",
        )
        return response

    def login_as_admin(self):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

    def login_as_role(self, role_name, *, username):
        user = get_user_model().objects.create_user(username=username, password="strong-password-123")
        group, _ = Group.objects.get_or_create(name=role_name)
        user.groups.add(group)
        self.client.force_login(user)
        return user

    def ajax_post(self, url, data=None):
        return self.client.post(
            url,
            data or {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def enable_device_access_for(self, *users):
        policy = DeviceApprovalPolicy.get_solo()
        policy.enabled = True
        policy.save()
        policy.target_users.set(users)
        return policy

    def create_device_credential(
        self,
        *,
        user,
        status=StaffDeviceCredentialStatus.APPROVED,
        credential_id="credential-1",
        device_label="Ward desktop",
        trusted_token=None,
    ):
        credential = StaffDeviceCredential.objects.create(
            user=user,
            status=status,
            device_label=device_label,
            credential_id=credential_id,
            public_key="public-key",
            sign_count=1,
            user_agent="Test Browser",
            approved_at=timezone.now() if status == StaffDeviceCredentialStatus.APPROVED else None,
            last_used_at=timezone.now() if status == StaffDeviceCredentialStatus.APPROVED else None,
        )
        if trusted_token:
            credential.trusted_token_hash = hashlib.sha256(trusted_token.encode("utf-8")).hexdigest()
            credential.trusted_token_created_at = timezone.now()
            credential.save(update_fields=["trusted_token_hash", "trusted_token_created_at"])
        return credential

    def fake_registration_webauthn_deps(self, *, credential_id=b"registration-credential", public_key=b"public-key"):
        class DummyRegistrationCredential:
            @staticmethod
            def parse_raw(value):
                return value

        class DummyDescriptor:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class DummyCredentialType:
            PUBLIC_KEY = "public-key"

        options = type("FakeOptions", (), {"challenge": b"register-challenge"})()
        verification = type(
            "FakeRegistrationVerification",
            (),
            {
                "credential_id": credential_id,
                "credential_public_key": public_key,
                "sign_count": 4,
                "credential_device_type": "single_device",
                "credential_backed_up": False,
                "aaguid": "",
            },
        )()
        return {
            "RegistrationCredential": DummyRegistrationCredential,
            "PublicKeyCredentialDescriptor": DummyDescriptor,
            "PublicKeyCredentialType": DummyCredentialType,
            "base64url_to_bytes": lambda value: b"decoded",
            "generate_registration_options": lambda **kwargs: options,
            "options_to_json": lambda options: json.dumps({"challenge": "register-challenge", "user": {"id": "1"}}),
            "verify_registration_response": lambda **kwargs: verification,
        }

    def fake_authentication_webauthn_deps(self, *, new_sign_count=11):
        class DummyAuthenticationCredential:
            @staticmethod
            def parse_raw(value):
                return value

        class DummyDescriptor:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class DummyCredentialType:
            PUBLIC_KEY = "public-key"

        class DummyUserVerificationRequirement:
            REQUIRED = "required"

        options = type("FakeOptions", (), {"challenge": b"auth-challenge"})()
        verification = type("FakeAuthenticationVerification", (), {"new_sign_count": new_sign_count})()
        return {
            "AuthenticationCredential": DummyAuthenticationCredential,
            "PublicKeyCredentialDescriptor": DummyDescriptor,
            "PublicKeyCredentialType": DummyCredentialType,
            "UserVerificationRequirement": DummyUserVerificationRequirement,
            "base64url_to_bytes": lambda value: b"decoded",
            "generate_authentication_options": lambda **kwargs: options,
            "options_to_json": lambda options: json.dumps(
                {"challenge": "auth-challenge", "allowCredentials": [{"id": "approved-credential", "type": "public-key"}]}
            ),
            "verify_authentication_response": lambda **kwargs: verification,
        }

    def create_recent_case(
        self,
        *,
        created_at=None,
        diagnosis="Fresh diagnosis",
        notes="",
        first_name="Recent",
        last_name="Patient",
        gender=Gender.FEMALE,
        age=32,
    ):
        self.case_sequence += 1
        case = Case.objects.create(
            uhid=f"UH-RECENT-{self.case_sequence:03d}",
            first_name=f"{first_name}{self.case_sequence}",
            last_name=last_name,
            phone_number=f"8{self.case_sequence:09d}",
            category=self.surgery,
            subcategory=CaseSubcategory.GENERAL_SURGERY,
            status=CaseStatus.ACTIVE,
            gender=gender,
            age=age,
            diagnosis=diagnosis,
            notes=notes,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        if created_at is not None:
            Case.objects.filter(pk=case.pk).update(created_at=created_at)
        return Case.objects.get(pk=case.pk)

    def create_bundle_case(
        self,
        *,
        uhid,
        first_name="Bundle",
        last_name="Patient",
        phone_number="9000000001",
        category=None,
        created_by=None,
        **overrides,
    ):
        category = category or self.surgery
        created_by = created_by or self.user
        defaults = {
            "uhid": uhid,
            "first_name": first_name,
            "last_name": last_name,
            "phone_number": phone_number,
            "category": category,
            "status": CaseStatus.ACTIVE,
            "created_by": created_by,
        }
        category_name = category.name.upper()
        if category_name == "ANC":
            defaults.update(
                {
                    "lmp": timezone.localdate() - timedelta(days=70),
                    "edd": timezone.localdate() + timedelta(days=200),
                }
            )
        elif category_name == "SURGERY":
            defaults.update(
                {
                    "subcategory": CaseSubcategory.GENERAL_SURGERY,
                    "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                    "review_date": timezone.localdate() + timedelta(days=7),
                }
            )
        else:
            defaults.update(
                {
                    "subcategory": default_case_subcategory_for_category_name(category.name),
                    "review_date": timezone.localdate() + timedelta(days=7),
                }
            )
        defaults.update(overrides)
        return Case.objects.create(**defaults)

    def build_patient_bundle_bytes(self):
        archive_bytes, _, _ = database_bundle.create_bundle_archive()
        return archive_bytes

    def rewrite_bundle(self, bundle_bytes, *, payload_mutator=None, manifest_mutator=None, refresh_manifest=True):
        with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as bundle_zip:
            payload = json.loads(bundle_zip.read(database_bundle.PATIENT_DATA_FILENAME).decode("utf-8"))
            manifest = json.loads(bundle_zip.read(database_bundle.MANIFEST_FILENAME).decode("utf-8"))

        if payload_mutator:
            payload_mutator(payload)

        patient_data_bytes = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
        if refresh_manifest:
            manifest["counts"] = database_bundle.compute_payload_counts(payload)
            manifest["patient_data_sha256"] = hashlib.sha256(patient_data_bytes).hexdigest()
        if manifest_mutator:
            manifest_mutator(manifest)

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle_zip:
            bundle_zip.writestr(database_bundle.PATIENT_DATA_FILENAME, patient_data_bytes)
            bundle_zip.writestr(
                database_bundle.MANIFEST_FILENAME,
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8"),
            )
        return archive.getvalue()

    def build_theme_post_data(self, *, token_overrides=None, category_overrides=None):
        token_values = flatten_theme_tokens(merge_theme_tokens(ThemeSettings.get_solo().tokens))
        if token_overrides:
            token_values.update(token_overrides)

        categories = list(DepartmentConfig.objects.order_by("name"))
        post_data = {"action": "save", **token_values}
        post_data.update(
            {
                "categories-TOTAL_FORMS": str(len(categories)),
                "categories-INITIAL_FORMS": str(len(categories)),
                "categories-MIN_NUM_FORMS": "0",
                "categories-MAX_NUM_FORMS": "1000",
            }
        )
        category_overrides = category_overrides or {}
        for index, category in enumerate(categories):
            colors = category_overrides.get(category.name, {})
            post_data[f"categories-{index}-id"] = str(category.pk)
            post_data[f"categories-{index}-theme_bg_color"] = colors.get("bg", category.theme_bg_color)
            post_data[f"categories-{index}-theme_text_color"] = colors.get("text", category.theme_text_color)
        return post_data

    def test_case_list_pagination_is_active(self):
        self.client.force_login(self.user)
        for index in range(30):
            Case.objects.create(
                uhid=f"UH-PAGE-{index:03d}",
                first_name="Paginated",
                last_name=f"Case {index}",
                phone_number=f"9{index:09d}",
                category=self.surgery,
                status=CaseStatus.ACTIVE,
                surgical_pathway=SurgicalPathway.SURVEILLANCE,
                review_date=timezone.localdate() + timedelta(days=10),
                created_by=self.user,
            )

        first_page = self.client.get(reverse("patients:case_list"))
        second_page = self.client.get(reverse("patients:case_list"), {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertTrue(first_page.context["is_paginated"])
        self.assertEqual(first_page.context["paginator"].per_page, 25)
        self.assertEqual(len(first_page.context["cases"]), 25)
        self.assertEqual(len(second_page.context["cases"]), 5)

    def test_case_list_query_count_stays_bounded_for_filtered_request(self):
        self.client.force_login(self.user)
        assignee = get_user_model().objects.create_user(username="assignee", password="strong-password-123")
        today = timezone.localdate()

        for index in range(30):
            case = Case.objects.create(
                uhid=f"UH-QL-{index:03d}",
                first_name="Perf",
                last_name=f"List {index}",
                phone_number=f"8{index:09d}",
                category=self.surgery,
                status=CaseStatus.ACTIVE,
                place="Chennai",
                surgical_pathway=SurgicalPathway.SURVEILLANCE,
                review_date=today + timedelta(days=14),
                created_by=self.user,
            )
            Task.objects.create(
                case=case,
                title="Assigned follow-up",
                due_date=today + timedelta(days=index % 7),
                assigned_user=assignee if index % 2 == 0 else None,
                created_by=self.user,
            )

        response = self.assert_max_queries(
            10,
            reverse("patients:case_list"),
            {
                "q": "Perf",
                "status": CaseStatus.ACTIVE,
                "category": str(self.surgery.id),
                "assigned_user": str(assignee.id),
                "due_start": (today - timedelta(days=1)).isoformat(),
                "due_end": (today + timedelta(days=10)).isoformat(),
                "page": "1",
            },
        )

        self.assertIn("q=Perf", response.context["filter_querystring"])
        self.assertNotIn("page=", response.context["filter_querystring"])

    def test_case_list_category_group_filter_matches_dashboard_buckets(self):
        self.client.force_login(self.user)
        non_surgical_hyphen, _ = DepartmentConfig.objects.get_or_create(name="Non-Surgical")
        medicine_category, _ = DepartmentConfig.objects.get_or_create(name="Medicine")
        today = timezone.localdate()

        anc_active = Case.objects.create(
            uhid="UH-GROUP-ANC-ACT",
            first_name="Anc",
            last_name="Active",
            phone_number="8123000001",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=today - timedelta(days=70),
            edd=today + timedelta(days=200),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-GROUP-ANC-COMP",
            first_name="Anc",
            last_name="Completed",
            phone_number="8123000002",
            category=self.anc,
            status=CaseStatus.COMPLETED,
            lmp=today - timedelta(days=65),
            edd=today + timedelta(days=205),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-GROUP-SURG-ACT",
            first_name="Surgery",
            last_name="Active",
            phone_number="8123000003",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=today + timedelta(days=12),
            created_by=self.user,
        )
        non_surgical_one = Case.objects.create(
            uhid="UH-GROUP-NS-ACT-1",
            first_name="Non",
            last_name="Hyphen",
            phone_number="8123000004",
            category=non_surgical_hyphen,
            status=CaseStatus.ACTIVE,
            review_date=today + timedelta(days=9),
            created_by=self.user,
        )
        non_surgical_two = Case.objects.create(
            uhid="UH-GROUP-NS-ACT-2",
            first_name="Medi",
            last_name="Cine",
            phone_number="8123000005",
            category=medicine_category,
            status=CaseStatus.ACTIVE,
            review_date=today + timedelta(days=11),
            created_by=self.user,
        )

        anc_response = self.client.get(
            reverse("patients:case_list"),
            {"status": CaseStatus.ACTIVE, "category_group": "anc"},
        )
        non_surgical_response = self.client.get(
            reverse("patients:case_list"),
            {"status": CaseStatus.ACTIVE, "category_group": "non_surgical"},
        )

        anc_ids = {case.id for case in anc_response.context["cases"]}
        non_surgical_ids = {case.id for case in non_surgical_response.context["cases"]}

        self.assertEqual(anc_response.status_code, 200)
        self.assertEqual(non_surgical_response.status_code, 200)
        self.assertEqual(anc_ids, {anc_active.id})
        self.assertEqual(non_surgical_ids, {non_surgical_one.id, non_surgical_two.id})
        self.assertIn("category_group=anc", anc_response.context["filter_querystring"])
        self.assertIn("category_group=non_surgical", non_surgical_response.context["filter_querystring"])

    def test_case_list_search_matches_diagnosis_case_notes_and_note_logs_without_duplicates(self):
        self.client.force_login(self.user)
        base_time = timezone.now()

        direct_case = Case.objects.create(
            uhid="UH-SEARCH-LIST-DIRECT",
            first_name="Direct",
            last_name="Match",
            phone_number="8011111111",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            diagnosis="Needle biopsy follow-up",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        case_notes_case = Case.objects.create(
            uhid="UH-SEARCH-LIST-NOTES",
            first_name="Case",
            last_name="Notes",
            phone_number="8022222222",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            notes="Needle follow-up summary in case notes for dressing review.",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        activity_case = Case.objects.create(
            uhid="UH-SEARCH-LIST-ACTIVITY",
            first_name="Timeline",
            last_name="Notes",
            phone_number="8033333333",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            diagnosis="Routine review",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        mixed_case = Case.objects.create(
            uhid="UH-SEARCH-LIST-MIXED",
            first_name="Mixed",
            last_name="Signals",
            phone_number="8044444444",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            diagnosis="Needle dressing change",
            notes="Needle note kept in case summary.",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        call_notes_case = Case.objects.create(
            uhid="UH-SEARCH-LIST-CALL",
            first_name="Call",
            last_name="Notes",
            phone_number="8055555555",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            diagnosis="Callback review",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )

        older_log = CaseActivityLog.objects.create(
            case=activity_case,
            user=self.user,
            event_type=ActivityEventType.NOTE,
            note="Older needle timeline note for initial review.",
        )
        newer_log = CaseActivityLog.objects.create(
            case=activity_case,
            user=self.user,
            event_type=ActivityEventType.NOTE,
            note="Latest needle timeline note for revised review plan.",
        )
        CaseActivityLog.objects.create(
            case=mixed_case,
            user=self.user,
            event_type=ActivityEventType.NOTE,
            note="Needle note that should not duplicate this case in results.",
        )
        CallLog.objects.create(
            case=call_notes_case,
            outcome=CallOutcome.NO_ANSWER,
            notes="Needle call note from outreach follow-up.",
            staff_user=self.user,
        )

        Case.objects.filter(pk=direct_case.pk).update(updated_at=base_time - timedelta(days=3))
        Case.objects.filter(pk=case_notes_case.pk).update(updated_at=base_time - timedelta(days=1))
        Case.objects.filter(pk=activity_case.pk).update(updated_at=base_time)
        Case.objects.filter(pk=mixed_case.pk).update(updated_at=base_time - timedelta(days=2))
        Case.objects.filter(pk=call_notes_case.pk).update(updated_at=base_time + timedelta(days=1))
        CaseActivityLog.objects.filter(pk=older_log.pk).update(created_at=base_time - timedelta(days=2))
        CaseActivityLog.objects.filter(pk=newer_log.pk).update(created_at=base_time - timedelta(hours=1))

        response = self.client.get(reverse("patients:case_list"), {"q": "needle"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["search_mode"])
        self.assertEqual(response.context["search_total_count"], 5)
        ordered_ids = [case.id for case in response.context["cases"]]
        self.assertLess(ordered_ids.index(direct_case.id), ordered_ids.index(case_notes_case.id))
        self.assertLess(ordered_ids.index(mixed_case.id), ordered_ids.index(case_notes_case.id))
        self.assertLess(ordered_ids.index(case_notes_case.id), ordered_ids.index(activity_case.id))
        self.assertLess(ordered_ids.index(activity_case.id), ordered_ids.index(call_notes_case.id))
        self.assertEqual(ordered_ids.count(mixed_case.id), 1)
        case_notes_result = next(case for case in response.context["cases"] if case.id == case_notes_case.id)
        activity_result = next(case for case in response.context["cases"] if case.id == activity_case.id)
        call_result = next(case for case in response.context["cases"] if case.id == call_notes_case.id)
        self.assertIn("Needle follow-up summary in case notes", case_notes_result.search_note_snippet)
        self.assertIn("Latest needle timeline note", activity_result.search_note_snippet)
        self.assertIn("Needle call note from outreach follow-up.", call_result.search_note_snippet)
        self.assertContains(response, 'Results for "needle"')

    def test_case_list_search_supports_multiple_category_group_filters(self):
        self.client.force_login(self.user)
        non_surgical, _ = DepartmentConfig.objects.get_or_create(name="Medicine")
        today = timezone.localdate()

        anc_case = Case.objects.create(
            uhid="UH-SEARCH-MULTI-ANC",
            first_name="Harbor",
            last_name="Anc",
            phone_number="8055555555",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            place="Harbor Town",
            lmp=today - timedelta(days=60),
            edd=today + timedelta(days=210),
            created_by=self.user,
        )
        surgery_case = Case.objects.create(
            uhid="UH-SEARCH-MULTI-SURG",
            first_name="Harbor",
            last_name="Surgery",
            phone_number="8066666666",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            place="Harbor Town",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=today + timedelta(days=7),
            created_by=self.user,
        )
        non_surgical_case = Case.objects.create(
            uhid="UH-SEARCH-MULTI-NS",
            first_name="Harbor",
            last_name="Medicine",
            phone_number="8077777777",
            category=non_surgical,
            status=CaseStatus.ACTIVE,
            place="Harbor Town",
            review_date=today + timedelta(days=7),
            created_by=self.user,
        )

        response = self.client.get(
            reverse("patients:case_list"),
            {"q": "harbor", "category_group": ["anc", "non_surgical"]},
        )

        self.assertEqual(response.status_code, 200)
        result_ids = {case.id for case in response.context["cases"]}
        self.assertEqual(result_ids, {anc_case.id, non_surgical_case.id})
        self.assertNotIn(surgery_case.id, result_ids)
        self.assertEqual(response.context["filters"]["category_groups"], ["anc", "non_surgical"])
        self.assertIn("category_group=anc", response.context["filter_querystring"])
        self.assertIn("category_group=non_surgical", response.context["filter_querystring"])
        self.assertContains(response, 'Results for "harbor"')

    def test_dashboard_category_cards_link_to_active_case_filters(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:dashboard"))
        case_list_response = self.client.get(reverse("patients:case_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-dashboard-summary-grid")
        self.assertContains(response, "data-dashboard-summary-item", count=6)
        self.assertContains(response, "data-nav-stats-bar", count=1)
        self.assertContains(response, "data-nav-stats-item", count=6)
        self.assertContains(response, "?status=ACTIVE&category_group=anc")
        self.assertContains(response, "?status=ACTIVE&category_group=surgery")
        self.assertContains(response, "?status=ACTIVE&category_group=non_surgical")
        self.assertContains(response, "View active Medicine cases")
        self.assertNotContains(case_list_response, "data-nav-stats-bar")
        self.assertNotContains(case_list_response, "data-nav-stats-item")

    def test_dashboard_query_count_stays_bounded(self):
        self.client.force_login(self.user)
        non_surgical, _ = DepartmentConfig.objects.get_or_create(name="Medicine")
        today = timezone.localdate()

        anc_active = Case.objects.create(
            uhid="UH-DASH-ANC-ACT",
            first_name="Dash",
            last_name="AncActive",
            phone_number="7777000001",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=today - timedelta(days=70),
            edd=today + timedelta(days=200),
            created_by=self.user,
        )
        surgery_active = Case.objects.create(
            uhid="UH-DASH-SURG-ACT",
            first_name="Dash",
            last_name="SurgActive",
            phone_number="7777000002",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=today + timedelta(days=12),
            created_by=self.user,
        )
        non_surgical_active = Case.objects.create(
            uhid="UH-DASH-NS-ACT",
            first_name="Dash",
            last_name="NsActive",
            phone_number="7777000003",
            category=non_surgical,
            status=CaseStatus.ACTIVE,
            review_date=today + timedelta(days=8),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-DASH-COMP",
            first_name="Dash",
            last_name="Completed",
            phone_number="7777000004",
            category=self.surgery,
            status=CaseStatus.COMPLETED,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=today + timedelta(days=9),
            created_by=self.user,
        )

        Task.objects.create(case=anc_active, title="Today", due_date=today, status=TaskStatus.SCHEDULED, created_by=self.user)
        Task.objects.create(case=surgery_active, title="Upcoming", due_date=today + timedelta(days=3), status=TaskStatus.SCHEDULED, created_by=self.user)
        Task.objects.create(case=non_surgical_active, title="Overdue", due_date=today - timedelta(days=2), status=TaskStatus.SCHEDULED, created_by=self.user)
        Task.objects.create(case=non_surgical_active, title="Awaiting", due_date=today + timedelta(days=11), status=TaskStatus.AWAITING_REPORTS, created_by=self.user)
        Task.objects.create(case=surgery_active, title="Completed", due_date=today - timedelta(days=1), status=TaskStatus.COMPLETED, created_by=self.user)

        response = self.assert_max_queries(20, reverse("patients:dashboard"), {"week_offset": 0})

        self.assertEqual(response.context["anc_case_count"], 1)
        self.assertEqual(response.context["surgery_case_count"], 1)
        self.assertEqual(response.context["non_surgical_case_count"], 1)
        self.assertContains(response, 'data-dashboard-module="today"')
        self.assertContains(response, 'data-dashboard-module="recent"')
        self.assertContains(response, 'data-dashboard-module="overdue"')
        self.assertContains(response, 'data-dashboard-module="awaiting"')

    def test_dashboard_recent_cases_panel_orders_latest_first_limits_to_ten_and_renders_above_overdue(self):
        self.client.force_login(self.user)
        base_time = timezone.now()
        created_cases = []
        long_diagnosis = "Very long dashboard diagnosis text that should truncate cleanly in the recent patient list."
        for index in range(12):
            created_cases.append(
                self.create_recent_case(
                    created_at=base_time - timedelta(minutes=index),
                    diagnosis=long_diagnosis if index == 0 else f"Diagnosis {index}",
                    first_name=f"Recent{index}",
                )
            )

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        recent_cases = response.context["recent_cases"]
        self.assertEqual(len(recent_cases), 12)
        self.assertEqual([entry["id"] for entry in recent_cases], [case.id for case in created_cases])
        self.assertEqual(recent_cases[0]["first_name"], created_cases[0].first_name)
        self.assertTrue(recent_cases[0]["is_new_today"])
        self.assertTrue(recent_cases[0]["can_edit"])
        self.assertTrue(recent_cases[0]["diagnosis_short"].endswith("..."))
        content = response.content.decode()
        recent_section_match = re.search(r'<section[^>]+data-recent-case-panel[^>]*>.*?</section>', content, re.S)
        overdue_section_match = re.search(r'<section[^>]+data-dashboard-module="overdue"[^>]*>.*?</section>', content, re.S)
        self.assertIsNotNone(recent_section_match)
        self.assertIsNotNone(overdue_section_match)
        section_html = recent_section_match.group(0)
        self.assertLess(recent_section_match.start(), overdue_section_match.start())
        self.assertIn('data-dashboard-module="recent"', section_html)
        self.assertEqual(section_html.count("data-recent-case-row"), 12)
        self.assertEqual(len(re.findall(r"data-recent-case-row[^>]*hidden", section_html)), 2)
        self.assertIn("data-recent-case-detail", section_html)
        self.assertNotIn("recentCaseModal", section_html)
        self.assertNotIn("shown", section_html)
        self.assertIn(">Expand<", section_html)
        self.assertIn(recent_cases[0]["sex_age"], section_html)
        self.assertIn(recent_cases[0]["created_at_short_display"], section_html)
        self.assertNotIn(f"Added {recent_cases[0]['created_at_display']}", section_html)
        self.assertNotIn("Update case notes and review tasks without leaving the dashboard.", content)

    def test_dashboard_recent_cases_panel_shows_empty_state_for_doctor(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_recent_cases_panel"])
        self.assertEqual(response.context["recent_cases"], [])
        self.assertContains(response, "No recent patients added.")
        section_match = re.search(r'<section[^>]+data-recent-case-panel[^>]*>.*?</section>', response.content.decode(), re.S)
        self.assertIsNotNone(section_match)
        section_html = section_match.group(0)
        self.assertNotIn("data-recent-case-toggle", section_html)
        self.assertNotIn(">Expand<", section_html)

    def test_dashboard_recent_cases_panel_is_hidden_for_non_recent_roles(self):
        self.login_as_role("Nurse", username="nurse_recent_panel")
        self.create_recent_case()

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_recent_cases_panel"])
        self.assertFalse(response.context["can_edit_recent_cases"])
        self.assertNotContains(response, "Recently Added")

    def test_dashboard_recent_cases_panel_is_read_only_for_reception(self):
        self.login_as_role("Reception", username="reception_recent_panel")
        created_case = self.create_recent_case(notes="Front desk note")

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_recent_cases_panel"])
        self.assertFalse(response.context["can_edit_recent_cases"])
        self.assertEqual(response.context["recent_cases"][0]["id"], created_case.id)
        self.assertFalse(response.context["recent_cases"][0]["can_edit"])

    def test_dashboard_recent_cases_panel_is_editable_for_full_capability_staff_role(self):
        RoleSetting.objects.update_or_create(
            role_name="Staff",
            defaults={
                "can_case_create": True,
                "can_case_edit": True,
                "can_task_create": True,
                "can_task_edit": True,
                "can_note_add": True,
                "can_manage_settings": False,
            },
        )
        self.login_as_role("Staff", username="staff_recent_panel")
        created_case = self.create_recent_case(notes="Staff note")

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_recent_cases_panel"])
        self.assertTrue(response.context["can_edit_recent_cases"])
        self.assertEqual(response.context["recent_cases"][0]["id"], created_case.id)
        self.assertTrue(response.context["recent_cases"][0]["can_edit"])

    def test_recent_cases_api_clamps_limit_and_returns_minimal_payload(self):
        self.client.force_login(self.user)
        base_time = timezone.now()
        created_cases = [
            self.create_recent_case(created_at=base_time - timedelta(minutes=index), diagnosis=f"Diagnosis {index}")
            for index in range(12)
        ]
        Task.objects.create(
            case=created_cases[0],
            title="Recent task",
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            notes="Needs review",
            created_by=self.user,
        )

        response = self.client.get(
            reverse("patients:recent_cases"),
            {"limit": "99"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 10)
        first_result = payload["results"][0]
        self.assertEqual(first_result["id"], created_cases[0].id)
        self.assertTrue(
            {
                "id",
                "name",
                "first_name",
                "short_name",
                "age_label",
                "age_number",
                "gender_label",
                "gender_code",
                "sex_age",
                "diagnosis",
                "diagnosis_input",
                "diagnosis_short",
                "notes",
                "created_at",
                "created_at_short_display",
                "is_new_today",
                "can_edit",
                "category_name",
                "subcategory_name",
                "category_bg_color",
                "category_text_color",
                "category_border_color",
                "detail_url",
                "tasks",
            }.issubset(first_result.keys())
        )
        self.assertEqual(first_result["first_name"], created_cases[0].first_name)
        self.assertNotIn("phone_number", first_result)
        self.assertNotIn("place", first_result)
        self.assertTrue(
            {
                "id",
                "title",
                "due_date",
                "status",
                "status_label",
                "notes",
                "can_complete",
                "can_reschedule",
                "can_note",
            }.issubset(first_result["tasks"][0].keys())
        )

        all_response = self.client.get(
            reverse("patients:recent_cases"),
            {"limit": "all"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(len(all_response.json()["results"]), 12)

    def test_recent_cases_api_is_forbidden_for_non_recent_roles(self):
        self.login_as_role("Nurse", username="nurse_recent_api")

        response = self.client.get(
            reverse("patients:recent_cases"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 403)

    def test_dashboard_nav_shows_new_case_and_quick_entry_for_case_create_roles(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("patients:case_create"))
        self.assertContains(response, reverse("patients:case_quick_create"))
        self.assertContains(response, 'class="btn btn-sm app-nav-action--new-case"')
        self.assertContains(response, 'class="btn btn-sm app-nav-action--quick-entry"')
        self.assertContains(response, f'href="{reverse("patients:settings")}"')
        self.assertContains(response, 'aria-label="Settings"', count=1)
        self.assertContains(response, f'action="{reverse("logout")}"')
        self.assertContains(response, 'aria-label="Logout"', count=1)
        self.assertNotContains(response, 'class="btn btn-sm btn-outline-light" href="{0}"'.format(reverse("patients:settings")))
        self.assertNotContains(response, 'class="btn btn-sm btn-light w-100">Logout')

    def test_dashboard_nav_hides_case_create_actions_without_case_create_capability(self):
        self.login_as_role("Nurse", username="nurse_nav")

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("patients:case_create"))
        self.assertNotContains(response, reverse("patients:case_quick_create"))

    def test_quick_case_create_view_is_forbidden_without_case_create_capability(self):
        self.login_as_role("Nurse", username="nurse_quick_create")

        response = self.client.get(reverse("patients:case_quick_create"))

        self.assertEqual(response.status_code, 403)

    def test_quick_case_create_view_hides_subcategory_until_category_has_options(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:case_quick_create"))
        response_text = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="subcategory"')
        self.assertContains(response, 'name="prefix"')
        self.assertContains(response, "data-quick-entry-subcategory-wrapper")
        self.assertContains(response, '"help_text": "Optional for quick entry. Choose the surgical specialty if known."')
        self.assertRegex(response_text, r"data-quick-entry-subcategory-wrapper\s+hidden")
        self.assertNotContains(response, "Only used for Surgery or Medicine.")

    def test_quick_case_create_invalid_surgery_submission_keeps_subcategory_visible(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_quick_create"),
            {
                "prefix": CasePrefix.MS,
                "first_name": "Visible",
                "age": "31",
                "gender": Gender.FEMALE,
                "category": self.surgery.id,
                "review_date": "",
                "diagnosis": "",
            },
        )
        response_text = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Optional for quick entry. Choose the surgical specialty if known.")
        self.assertNotRegex(response_text, r"data-quick-entry-subcategory-wrapper\s+hidden")

    def test_case_create_view_is_forbidden_without_case_create_capability(self):
        self.login_as_role("Nurse", username="nurse_case_create")

        response = self.client.get(reverse("patients:case_create"))

        self.assertEqual(response.status_code, 403)

    def test_quick_case_create_saves_minimal_case_and_tasks(self):
        review_date = timezone.localdate() + timedelta(days=7)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_quick_create"),
            {
                "prefix": CasePrefix.MRS,
                "first_name": "Lalitha",
                "age": "42",
                "gender": Gender.FEMALE,
                "diagnosis": "Thyroid swelling",
                "category": self.surgery.id,
                "review_date": review_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(metadata__entry_mode="quick_entry", first_name="Lalitha")
        self.assertRegex(case.uhid, r"^QE-\d{8}-\d{3}$")
        self.assertEqual(case.prefix, CasePrefix.MRS)
        self.assertEqual(case.patient_name, "Mrs. Lalitha")
        self.assertEqual(case.last_name, "")
        self.assertEqual(case.phone_number, "")
        self.assertEqual(case.alternate_phone_number, "")
        self.assertEqual(case.status, CaseStatus.ACTIVE)
        self.assertEqual(case.review_date, review_date)
        self.assertEqual(case.subcategory, "")
        self.assertEqual(case.metadata["entry_mode"], "quick_entry")
        self.assertTrue(case.metadata["details_pending"])
        self.assertTrue(case.tasks.filter(title=QUICK_ENTRY_DETAILS_TASK_TITLE, due_date=review_date).exists())
        self.assertTrue(case.tasks.filter(title="Surveillance Review").exists())
        self.assertTrue(
            case.activity_logs.filter(note__icontains="Quick entry created with 1 starter task(s)").exists()
        )

    def test_quick_case_create_accepts_optional_subcategory_when_provided(self):
        review_date = timezone.localdate() + timedelta(days=8)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_quick_create"),
            {
                "prefix": CasePrefix.MS,
                "first_name": "Optional",
                "age": "39",
                "gender": Gender.FEMALE,
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.ORTHOPEDICS,
                "review_date": review_date.isoformat(),
                "diagnosis": "Quick entry with known specialty",
            },
        )

        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(metadata__entry_mode="quick_entry", first_name="Optional")
        self.assertEqual(case.subcategory, CaseSubcategory.ORTHOPEDICS)

    def test_quick_case_create_allows_anc_without_full_anc_fields(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_quick_create"),
            {
                "prefix": CasePrefix.MRS,
                "first_name": "Revathi",
                "age": "24",
                "gender": Gender.FEMALE,
                "diagnosis": "ANC follow-up pending full details",
                "category": self.anc.id,
                "review_date": (timezone.localdate() + timedelta(days=4)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(first_name="Revathi", metadata__entry_mode="quick_entry")
        self.assertEqual(case.category, self.anc)
        self.assertTrue(case.tasks.filter(title=QUICK_ENTRY_DETAILS_TASK_TITLE).exists())
        self.assertGreater(case.tasks.count(), 1)
        self.assertFalse(case.tasks.filter(title=RCH_REMINDER_TASK_TITLE).exists())

    def test_quick_case_create_invalid_submission_shows_inline_errors(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_quick_create"),
            {
                "prefix": "",
                "first_name": "",
                "age": "",
                "gender": "",
                "diagnosis": "",
                "category": "",
                "review_date": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid-feedback")
        self.assertContains(response, "This field is required.")
        self.assertContains(response, 'name="prefix"')

    def test_quick_case_create_requires_prefix(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_quick_create"),
            {
                "prefix": "",
                "first_name": "NoPrefix",
                "age": "26",
                "gender": Gender.FEMALE,
                "diagnosis": "Prefix missing",
                "category": self.surgery.id,
                "review_date": (timezone.localdate() + timedelta(days=5)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertFalse(Case.objects.filter(first_name="NoPrefix").exists())

    def test_quick_entry_cases_show_phone_pending_fallback_in_detail_and_list(self):
        case = Case.objects.create(
            uhid="QE-20260318-001",
            first_name="Pending",
            last_name="",
            age=32,
            gender=Gender.FEMALE,
            phone_number="",
            category=self.medicine,
            review_date=timezone.localdate() + timedelta(days=5),
            diagnosis="Pending phone details",
            created_by=self.user,
            metadata={"entry_mode": "quick_entry", "details_pending": True},
        )

        self.client.force_login(self.user)
        detail_response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))
        list_response = self.client.get(reverse("patients:case_list"))

        self.assertContains(detail_response, "Phone pending")
        self.assertContains(list_response, "Phone pending")

    def test_create_anc_case_autogenerates_tasks(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH222",
                "prefix": CasePrefix.MS,
                "first_name": "Grace",
                "last_name": "Hopper",
                "phone_number": "9876543210",
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "28",
                "lmp": timezone.localdate() - timedelta(days=60),
                "edd": timezone.localdate() + timedelta(days=210),
                "rch_bypass": "on",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(uhid="UH222")
        self.assertGreaterEqual(case.tasks.count(), 20)

    def test_case_create_sets_created_by_and_logs_case_created_activity(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH-CREATE-ACTIVITY",
                "prefix": CasePrefix.MR,
                "first_name": "Log",
                "last_name": "Check",
                "phone_number": "9876543200",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "age": "38",
                "surgical_pathway": SurgicalPathway.PLANNED_SURGERY,
                "surgery_date": (timezone.localdate() + timedelta(days=7)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(uhid="UH-CREATE-ACTIVITY")
        self.assertEqual(case.created_by, self.user)
        self.assertTrue(case.activity_logs.filter(note__icontains="Case created with 5 starter task").exists())

    def test_anc_task_cannot_complete_before_due_date(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH999",
            first_name="Future",
            last_name="ANC",
            phone_number="9998887776",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=timezone.localdate() - timedelta(days=30),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )
        task = Task.objects.create(
            case=case,
            title="Future ANC Check",
            due_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        response = self.client.post(
            reverse("patients:task_edit", kwargs={"pk": task.pk}),
            {
                "title": task.title,
                "due_date": task.due_date.isoformat(),
                "status": TaskStatus.COMPLETED,
                "assigned_user": "",
                "task_type": task.task_type,
                "frequency_label": task.frequency_label,
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertNotEqual(task.status, TaskStatus.COMPLETED)

    def test_task_create_blocks_anc_completion_before_due_date(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH998",
            first_name="Future",
            last_name="Create",
            phone_number="9998887775",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=timezone.localdate() - timedelta(days=30),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:task_create", kwargs={"pk": case.pk}),
            {
                "title": "Future ANC Create",
                "due_date": (timezone.localdate() + timedelta(days=7)).isoformat(),
                "status": TaskStatus.COMPLETED,
                "assigned_user": "",
                "task_type": "CUSTOM",
                "frequency_label": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(case.tasks.filter(title="Future ANC Create").exists())

    def test_task_create_supports_ajax_json_and_redirect_fallback(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-TASK-AJAX",
            first_name="Task",
            last_name="Ajax",
            phone_number="9998887766",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=self.user,
        )
        due_date = timezone.localdate() + timedelta(days=2)

        ajax_response = self.ajax_post(
            reverse("patients:task_create", kwargs={"pk": case.pk}),
            {
                "title": "Ajax created task",
                "due_date": due_date.isoformat(),
                "status": TaskStatus.SCHEDULED,
                "assigned_user": "",
                "task_type": TaskType.CUSTOM,
                "frequency_label": "",
                "notes": "Created via XHR",
            },
        )
        redirect_response = self.client.post(
            reverse("patients:task_create", kwargs={"pk": case.pk}),
            {
                "title": "Redirect created task",
                "due_date": (due_date + timedelta(days=1)).isoformat(),
                "status": TaskStatus.SCHEDULED,
                "assigned_user": "",
                "task_type": TaskType.CUSTOM,
                "frequency_label": "",
                "notes": "Created via redirect",
            },
        )

        self.assertEqual(ajax_response.status_code, 200)
        self.assertEqual(redirect_response.status_code, 302)

        ajax_data = ajax_response.json()
        self.assertEqual(ajax_data["message"], "Task added.")
        self.assertEqual(ajax_data["task"]["title"], "Ajax created task")
        self.assertEqual(ajax_data["task"]["due_date"], due_date.isoformat())
        self.assertEqual(ajax_data["task"]["status"], TaskStatus.SCHEDULED)
        self.assertTrue(case.tasks.filter(title="Ajax created task").exists())
        self.assertTrue(case.tasks.filter(title="Redirect created task").exists())

    def test_task_create_ajax_validation_errors_return_json(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-TASK-AJAX-INVALID",
            first_name="Task",
            last_name="Invalid",
            phone_number="9998887765",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=self.user,
        )

        response = self.ajax_post(
            reverse("patients:task_create", kwargs={"pk": case.pk}),
            {
                "title": "",
                "due_date": "",
                "status": TaskStatus.SCHEDULED,
                "assigned_user": "",
                "task_type": TaskType.CUSTOM,
                "frequency_label": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["message"], "Could not add task. Please check the inputs.")
        self.assertIn("title", payload["errors"])
        self.assertIn("due_date", payload["errors"])

    def test_case_detail_allows_note_only_role(self):
        ensure_default_role_settings()
        caller_group, _ = Group.objects.get_or_create(name="Caller")
        caller_user = get_user_model().objects.create_user(username="caller", password="strong-password-123")
        caller_user.groups.add(caller_group)
        case = Case.objects.create(
            uhid="UH-CALLER",
            first_name="Note",
            last_name="Only",
            phone_number="9876511111",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        self.client.force_login(caller_user)
        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)

    def test_case_detail_actionable_table_omits_completed_on_column(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-COMP-COL",
            first_name="Column",
            last_name="Check",
            phone_number="9876504441",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Review",
            due_date=timezone.localdate(),
            assigned_user=self.user,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        actionable_start = html.index("Actionable Tasks")
        all_tasks_start = html.index("All Tasks")
        actionable_html = html[actionable_start:all_tasks_start]
        self.assertNotIn("<th>Completed On</th>", actionable_html)
        self.assertNotIn("<th>Assigned</th>", actionable_html)
        self.assertContains(response, "<th>Completed On</th>", html=True)

    def test_case_detail_uses_high_risk_and_category_pill_classes(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-THEME-DETAIL",
            first_name="Theme",
            last_name="Detail",
            phone_number="9876504991",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            high_risk=True,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=4),
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "app-pill high-risk")
        self.assertContains(response, "category-surgery")

    def test_case_list_and_detail_show_subcategory_when_present(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-SUBCATEGORY-DETAIL",
            first_name="Sub",
            last_name="Category",
            phone_number="9876504990",
            category=self.surgery,
            subcategory=CaseSubcategory.ORTHOPEDICS,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )

        list_response = self.client.get(reverse("patients:case_list"))
        detail_response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertContains(list_response, "Orthopedics")
        self.assertContains(detail_response, "Orthopedics")

    def test_case_list_shows_category_pill_classes(self):
        self.client.force_login(self.user)
        non_surgical, _ = DepartmentConfig.objects.get_or_create(name="Medicine")
        Case.objects.create(
            uhid="UH-THEME-ANC",
            first_name="Anc",
            last_name="Chip",
            phone_number="9876504992",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=timezone.localdate() - timedelta(days=50),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-THEME-SUR",
            first_name="Surgery",
            last_name="Chip",
            phone_number="9876504993",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-THEME-NS",
            first_name="Medi",
            last_name="Cine",
            phone_number="9876504994",
            category=non_surgical,
            status=CaseStatus.ACTIVE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "category-anc")
        self.assertContains(response, "category-surgery")
        self.assertContains(response, "category-non-surgical")
        self.assertContains(response, "Medicine")

    def test_case_detail_uses_custom_completed_row_class_style(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-THEME-ROW",
            first_name="Row",
            last_name="Class",
            phone_number="9876504995",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Completed row style",
            due_date=timezone.localdate() - timedelta(days=1),
            status=TaskStatus.COMPLETED,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "case-task-history-row--completed")
        self.assertNotContains(response, "table-success")

    def test_case_detail_shows_all_tasks_master_list_with_filters(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-THEME-ALL-TASKS",
            first_name="All",
            last_name="Tasks",
            phone_number="9876504996",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Open task",
            due_date=timezone.localdate() + timedelta(days=1),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Completed task",
            due_date=timezone.localdate(),
            status=TaskStatus.COMPLETED,
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Cancelled task",
            due_date=timezone.localdate() + timedelta(days=2),
            status=TaskStatus.CANCELLED,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertContains(response, "All Tasks")
        self.assertEqual(response.context["overdue_task_count"], 0)
        self.assertEqual(response.context["open_task_count"], 1)
        self.assertEqual(response.context["completed_task_count"], 1)
        self.assertEqual(response.context["total_task_count"], 3)
        self.assertContains(response, 'data-task-filter')
        self.assertContains(response, 'data-task-bucket="open"')
        self.assertContains(response, 'data-task-bucket="completed"')
        self.assertContains(response, 'data-task-bucket="cancelled"')
        self.assertContains(response, 'data-testid="actionable-task-mobile-list"')
        self.assertContains(response, 'data-testid="all-task-mobile-list"')
        self.assertContains(response, 'data-testid="all-tasks-toggle"')
        self.assertContains(response, 'data-testid="all-tasks-panel"')
        self.assertContains(response, 'id="action-card-task"')
        self.assertContains(response, 'id="action-card-call"')
        self.assertContains(response, 'id="action-card-note"')
        self.assertContains(response, 'id="all-task-table"')
        self.assertEqual(html.count("<th>Completed On</th>"), 1)
        self.assertEqual(html.count('data-task-filter'), 3)
        self.assertNotContains(response, 'data-bs-target="#reschedule-')
        self.assertNotContains(response, 'data-bs-target="#note-')
        self.assertNotContains(response, "Upcoming queue")
        self.assertNotContains(response, "Overdue tasks rise to the top, then the next open tasks up to five.")
        self.assertContains(response, "Clinical Timeline")
        self.assertNotContains(response, "More Open Tasks")
        self.assertNotContains(response, "Completed / Cancelled History")

    def test_case_detail_locked_future_anc_task_keeps_reschedule_and_note_actions(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-THEME-LOCKED-ANC",
            first_name="Locked",
            last_name="ANC",
            phone_number="9876504998",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            gender=Gender.FEMALE,
            lmp=timezone.localdate() - timedelta(days=70),
            edd=timezone.localdate() + timedelta(days=210),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Future ANC task",
            due_date=timezone.localdate() + timedelta(days=5),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Locked until due date")
        html = response.content.decode("utf-8")
        actionable_start = html.index("Actionable Tasks")
        all_tasks_start = html.index("All Tasks")
        actionable_html = html[actionable_start:all_tasks_start]
        self.assertIn("Reschedule", actionable_html)
        self.assertIn("Note", actionable_html)
        self.assertNotIn("Complete", actionable_html)
        self.assertNotIn("task_quick_complete", actionable_html)

    def test_case_detail_uses_toned_overdue_row_class(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-THEME-OVERDUE",
            first_name="Over",
            last_name="Due",
            phone_number="9876504997",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Overdue task",
            due_date=timezone.localdate() - timedelta(days=1),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertContains(response, "case-task-row--overdue")
        self.assertNotRegex(html, r'class="[^"]*table-danger')

    def test_case_detail_completed_task_shows_completed_at_date(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-COMP-DATE",
            first_name="Completed",
            last_name="Timestamp",
            phone_number="9876504442",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        task = Task.objects.create(
            case=case,
            title="Completed task",
            due_date=timezone.localdate() - timedelta(days=2),
            status=TaskStatus.COMPLETED,
            assigned_user=self.user,
            created_by=self.user,
        )
        completed_at = timezone.make_aware(datetime(2026, 1, 15, 10, 30))
        Task.objects.filter(pk=task.pk).update(completed_at=completed_at)
        expected_date = timezone.localtime(completed_at).strftime("%d-%m-%y")

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, expected_date)

    def test_case_detail_completed_task_falls_back_to_due_date_when_completed_at_missing(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-COMP-FALLBACK",
            first_name="Completed",
            last_name="Fallback",
            phone_number="9876504443",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        due_date = timezone.localdate() - timedelta(days=3)
        task = Task.objects.create(
            case=case,
            title="Legacy completed task",
            due_date=due_date,
            status=TaskStatus.COMPLETED,
            assigned_user=self.user,
            created_by=self.user,
        )
        Task.objects.filter(pk=task.pk).update(completed_at=None)

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, due_date.strftime("%d-%m-%y"))

    def test_case_detail_non_completed_task_shows_dash_for_completed_on(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-COMP-DASH",
            first_name="Scheduled",
            last_name="Dash",
            phone_number="9876504444",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Scheduled task",
            due_date=timezone.localdate() + timedelta(days=1),
            status=TaskStatus.SCHEDULED,
            assigned_user=self.user,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">-</td>", html=False)

    def test_case_detail_shows_collapsed_action_center_and_timeline_filters(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-ACTION-01",
            first_name="Action",
            last_name="Center",
            phone_number="9876505111",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        task = Task.objects.create(
            case=case,
            title="Timeline task",
            due_date=timezone.localdate(),
            created_by=self.user,
        )
        CallLog.objects.create(
            case=case,
            task=task,
            outcome=CallOutcome.NO_ANSWER,
            notes="Called once",
            staff_user=self.user,
        )
        CaseActivityLog.objects.create(
            case=case,
            task=task,
            user=self.user,
            event_type=ActivityEventType.TASK,
            note="Task created for timeline",
        )
        CaseActivityLog.objects.create(
            case=case,
            user=self.user,
            event_type=ActivityEventType.NOTE,
            note="Nurse follow-up note",
        )
        CaseActivityLog.objects.create(
            case=case,
            task=task,
            user=self.user,
            event_type=ActivityEventType.TASK,
            note="Confirm visit timing [Task: Timeline task]",
        )

        response = self.client.get(
            reverse("patients:case_detail", kwargs={"pk": case.pk}),
            {"timeline": "notes", "show_logs": "1"},
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertContains(response, "Action Center")
        self.assertContains(response, "Add Task")
        self.assertContains(response, "Log Call")
        self.assertContains(response, "Add Note")
        self.assertContains(response, "Clinical Timeline")
        self.assertContains(response, 'data-testid="case-detail-shell"')
        self.assertContains(response, 'data-testid="case-detail-hero"')
        self.assertContains(response, 'data-testid="case-detail-module-row"')
        self.assertContains(response, 'data-testid="case-detail-workspace"')
        self.assertContains(response, 'data-testid="case-detail-sidebar"')
        self.assertContains(response, 'data-testid="case-detail-timeline"')
        self.assertNotContains(response, 'data-testid="case-detail-mobile-quick-actions"')
        self.assertContains(response, 'data-case-composer-trigger="task"')
        self.assertContains(response, 'data-case-composer-trigger="call"')
        self.assertContains(response, 'data-case-composer-trigger="note"')
        self.assertContains(response, 'data-case-active-pane=""')
        self.assertContains(response, 'data-case-composer-close')
        self.assertContains(response, 'name="status" value="SCHEDULED"', html=False)
        self.assertContains(response, 'name="assigned_user" value=""', html=False)
        self.assertContains(response, 'name="task_type" value="CUSTOM"', html=False)
        self.assertContains(response, 'name="frequency_label" value=""', html=False)
        self.assertContains(response, 'name="notes" value=""', html=False)
        self.assertNotContains(response, 'data-case-active-pane="task"')
        self.assertNotContains(response, 'data-case-active-pane="call"')
        self.assertNotContains(response, 'data-case-active-pane="note"')
        self.assertNotRegex(response.content.decode("utf-8"), r'data-case-composer-panel="(?:task|call|note)"[^>]*is-active')
        self.assertEqual(html.count('data-testid="case-task-editor"'), 1)
        self.assertEqual(html.count('data-task-editor-trigger="reschedule"'), 2)
        self.assertEqual(html.count('data-task-editor-trigger="note"'), 2)
        self.assertEqual(html.count('data-task-editor-form="reschedule"'), 1)
        self.assertEqual(html.count('data-task-editor-form="note"'), 1)
        self.assertNotRegex(html, r'id="reschedule-\d+"')
        self.assertNotRegex(html, r'id="note-\d+"')
        self.assertNotContains(response, "Upcoming queue")
        self.assertNotContains(response, "Pick a new due date without leaving the task workspace.")
        self.assertNotContains(response, "Add context that stays attached to this task in the case history.")
        self.assertContains(response, "Nurse follow-up note")
        self.assertContains(response, "Confirm visit timing [Task: Timeline task]")
        self.assertNotContains(response, "Task created for timeline")

    def test_case_detail_disables_restricted_action_cards_for_note_only_role(self):
        ensure_default_role_settings()
        caller_group, _ = Group.objects.get_or_create(name="Caller")
        caller_user = get_user_model().objects.create_user(username="caller-disabled", password="strong-password-123")
        caller_user.groups.add(caller_group)
        case = Case.objects.create(
            uhid="UH-CALLER-DISABLED",
            first_name="Note",
            last_name="Only",
            phone_number="9876511122",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        self.client.force_login(caller_user)
        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Action Center")
        self.assertContains(response, 'data-case-composer-trigger="task"')
        self.assertContains(response, 'data-case-composer-trigger="call"')
        self.assertContains(response, 'data-case-composer-trigger="note"')
        self.assertRegex(
            response.content.decode("utf-8"),
            r'data-case-composer-trigger="task"[^>]*(?:disabled|aria-disabled="true")',
        )
        self.assertNotContains(response, 'data-testid="case-detail-mobile-quick-actions"')

    def test_case_detail_call_log_task_select_shows_only_open_and_upcoming_tasks(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-CALL-SELECT",
            first_name="Call",
            last_name="Select",
            phone_number="9876511133",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        open_task = Task.objects.create(
            case=case,
            title="Open call task",
            due_date=timezone.localdate() + timedelta(days=1),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )
        awaiting_task = Task.objects.create(
            case=case,
            title="Awaiting call task",
            due_date=timezone.localdate() + timedelta(days=2),
            status=TaskStatus.AWAITING_REPORTS,
            created_by=self.user,
        )
        overdue_task = Task.objects.create(
            case=case,
            title="Overdue call task",
            due_date=timezone.localdate() - timedelta(days=2),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )
        completed_task = Task.objects.create(
            case=case,
            title="Completed call task",
            due_date=timezone.localdate() - timedelta(days=1),
            status=TaskStatus.COMPLETED,
            created_by=self.user,
        )
        cancelled_task = Task.objects.create(
            case=case,
            title="Cancelled call task",
            due_date=timezone.localdate() + timedelta(days=3),
            status=TaskStatus.CANCELLED,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        task_select_id = response.context["call_log_form"]["task"].id_for_label
        select_match = re.search(
            rf'<select[^>]*id="{re.escape(task_select_id)}"[^>]*>(.*?)</select>',
            response.content.decode("utf-8"),
            re.DOTALL,
        )
        self.assertIsNotNone(select_match)
        select_html = select_match.group(1)
        self.assertIn(open_task.title, select_html)
        self.assertIn(awaiting_task.title, select_html)
        self.assertNotIn(overdue_task.title, select_html)
        self.assertNotIn(completed_task.title, select_html)
        self.assertNotIn(cancelled_task.title, select_html)

    def test_case_detail_limits_prominent_tasks_to_five_open_tasks(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-ACTION-02",
            first_name="Open",
            last_name="Tasks",
            phone_number="9876505222",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        for index in range(7):
            Task.objects.create(
                case=case,
                title=f"Open task {index + 1}",
                due_date=timezone.localdate() + timedelta(days=index),
                created_by=self.user,
            )
        Task.objects.create(
            case=case,
            title="Closed task",
            due_date=timezone.localdate(),
            status=TaskStatus.COMPLETED,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["prominent_tasks"]), 5)
        self.assertTrue(response.context["remaining_open_groups"])

    def test_task_quick_complete_marks_completed_and_logs_task_activity(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-ACTION-03",
            first_name="Quick",
            last_name="Complete",
            phone_number="9876505333",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            created_by=self.user,
        )
        task = Task.objects.create(
            case=case,
            title="Quick complete task",
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        response = self.client.post(reverse("patients:task_quick_complete", kwargs={"pk": task.pk}))

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertTrue(
            CaseActivityLog.objects.filter(
                case=case,
                task=task,
                event_type=ActivityEventType.TASK,
                note__icontains="Task completed",
            ).exists()
        )

    def test_task_quick_reschedule_blocks_completed_tasks(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-ACTION-04",
            first_name="Quick",
            last_name="Reschedule",
            phone_number="9876505444",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            created_by=self.user,
        )
        task = Task.objects.create(
            case=case,
            title="Completed task",
            due_date=timezone.localdate(),
            status=TaskStatus.COMPLETED,
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:task_quick_reschedule", kwargs={"pk": task.pk}),
            {"due_date": (timezone.localdate() + timedelta(days=4)).isoformat()},
        )

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.due_date, timezone.localdate())

    def test_task_quick_reschedule_accepts_india_style_date_input(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-ACTION-04A",
            first_name="Quick",
            last_name="India Date",
            phone_number="9876505443",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            created_by=self.user,
        )
        task = Task.objects.create(
            case=case,
            title="Reschedule with dd/mm/yyyy",
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        new_due_date = timezone.localdate() + timedelta(days=4)
        response = self.client.post(
            reverse("patients:task_quick_reschedule", kwargs={"pk": task.pk}),
            {"due_date": new_due_date.strftime("%d/%m/%Y")},
        )

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.due_date, new_due_date)

    def test_task_quick_note_updates_task_and_logs_activity(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-ACTION-05",
            first_name="Quick",
            last_name="Note",
            phone_number="9876505555",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            created_by=self.user,
        )
        task = Task.objects.create(
            case=case,
            title="Task with note",
            due_date=timezone.localdate(),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:task_quick_note", kwargs={"pk": task.pk}),
            {"note": "Inline note update"},
        )

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.notes, "Inline note update")
        self.assertTrue(
            CaseActivityLog.objects.filter(
                case=case,
                task=task,
                event_type=ActivityEventType.TASK,
                note__icontains="Inline note update",
            ).exists()
        )

    def test_task_quick_actions_return_json_for_ajax_requests_and_keep_redirect_flow(self):
        self.client.force_login(self.user)
        case = self.create_recent_case(diagnosis="Task workflow")
        today = timezone.localdate()
        reschedule_task = Task.objects.create(
            case=case,
            title="Reschedule me",
            due_date=today + timedelta(days=1),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )
        note_task = Task.objects.create(
            case=case,
            title="Note me",
            due_date=today,
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )
        complete_task = Task.objects.create(
            case=case,
            title="Complete me",
            due_date=today,
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )
        redirect_task = Task.objects.create(
            case=case,
            title="Redirect me",
            due_date=today,
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        new_due_date = today + timedelta(days=5)
        reschedule_response = self.client.post(
            reverse("patients:task_quick_reschedule", kwargs={"pk": reschedule_task.pk}),
            {"due_date": new_due_date.isoformat()},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        note_response = self.client.post(
            reverse("patients:task_quick_note", kwargs={"pk": note_task.pk}),
            {"note": "Updated from modal"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        complete_response = self.client.post(
            reverse("patients:task_quick_complete", kwargs={"pk": complete_task.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        redirect_response = self.client.post(
            reverse("patients:task_quick_note", kwargs={"pk": redirect_task.pk}),
            {"note": "Classic redirect"},
        )

        self.assertEqual(reschedule_response.status_code, 200)
        self.assertEqual(note_response.status_code, 200)
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(redirect_response.status_code, 302)

        reschedule_task.refresh_from_db()
        note_task.refresh_from_db()
        complete_task.refresh_from_db()
        redirect_task.refresh_from_db()

        self.assertEqual(reschedule_task.due_date, new_due_date)
        self.assertEqual(note_task.notes, "Updated from modal")
        self.assertEqual(complete_task.status, TaskStatus.COMPLETED)
        self.assertEqual(redirect_task.notes, "Classic redirect")

        self.assertIn("case", reschedule_response.json())
        self.assertEqual(reschedule_response.json()["task"]["due_date"], new_due_date.isoformat())
        self.assertEqual(note_response.json()["task"]["notes"], "Updated from modal")
        self.assertEqual(complete_response.json()["task"]["status"], TaskStatus.COMPLETED)

    def test_add_case_note_supports_ajax_json_and_redirect_fallback(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-NOTE-AJAX",
            first_name="Note",
            last_name="Ajax",
            phone_number="9876505777",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=self.user,
        )

        ajax_response = self.ajax_post(
            reverse("patients:case_note_create", kwargs={"pk": case.pk}),
            {"note": "Created via XHR"},
        )
        redirect_response = self.client.post(
            reverse("patients:case_note_create", kwargs={"pk": case.pk}),
            {"note": "Created via redirect"},
        )

        self.assertEqual(ajax_response.status_code, 200)
        self.assertEqual(redirect_response.status_code, 302)
        self.assertEqual(ajax_response.json()["message"], "Note added.")
        self.assertTrue(case.activity_logs.filter(note="Created via XHR").exists())
        self.assertTrue(case.activity_logs.filter(note="Created via redirect").exists())

    def test_add_case_note_ajax_validation_errors_return_json(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-NOTE-AJAX-INVALID",
            first_name="Note",
            last_name="Invalid",
            phone_number="9876505778",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=self.user,
        )

        response = self.ajax_post(
            reverse("patients:case_note_create", kwargs={"pk": case.pk}),
            {"note": ""},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["message"], "Could not save note.")
        self.assertIn("note", payload["errors"])

    def test_add_call_log_supports_ajax_json_and_redirect_fallback(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-CALL-AJAX",
            first_name="Call",
            last_name="Ajax",
            phone_number="9876505888",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=self.user,
        )
        task = Task.objects.create(
            case=case,
            title="Call task",
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        ajax_response = self.ajax_post(
            reverse("patients:case_call_create", kwargs={"pk": case.pk}),
            {"task": task.pk, "outcome": CallOutcome.NO_ANSWER, "notes": "Created via XHR"},
        )
        redirect_response = self.client.post(
            reverse("patients:case_call_create", kwargs={"pk": case.pk}),
            {"task": task.pk, "outcome": CallOutcome.CALL_BACK_LATER, "notes": "Created via redirect"},
        )

        self.assertEqual(ajax_response.status_code, 200)
        self.assertEqual(redirect_response.status_code, 302)
        self.assertEqual(ajax_response.json()["message"], "Call outcome logged.")
        self.assertTrue(case.call_logs.filter(notes="Created via XHR").exists())
        self.assertTrue(case.call_logs.filter(notes="Created via redirect").exists())

    def test_add_call_log_ajax_validation_errors_return_json(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-CALL-AJAX-INVALID",
            first_name="Call",
            last_name="Invalid",
            phone_number="9876505889",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Call task invalid",
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        response = self.ajax_post(
            reverse("patients:case_call_create", kwargs={"pk": case.pk}),
            {"task": "", "outcome": CallOutcome.NO_ANSWER, "notes": "Missing task"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["message"], "Could not log call outcome.")
        self.assertIn("task", payload["errors"])

    def test_case_detail_marks_task_date_inputs_for_crayons_datepicker(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-ACTION-05A",
            first_name="Markup",
            last_name="Check",
            phone_number="9876505554",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Visible task",
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertContains(response, 'data-crayons-datepicker="true"', count=2)
        self.assertContains(response, 'data-crayons-datepicker-format="dd/MM/yyyy"', count=2)
        self.assertContains(response, 'data-crayons-datepicker-show-footer="false"', count=2)
        self.assertContains(response, 'id="task-shared-reschedule-date"')

    def test_recent_case_update_persists_changes_and_logs_activity(self):
        self.client.force_login(self.user)
        case = self.create_recent_case(diagnosis="Old diagnosis", notes="Old note")

        response = self.client.post(
            reverse("patients:recent_case_update", kwargs={"pk": case.pk}),
            {"diagnosis": "Updated diagnosis", "notes": "Updated note"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        case.refresh_from_db()
        self.assertEqual(case.diagnosis, "Updated diagnosis")
        self.assertEqual(case.notes, "Updated note")
        self.assertEqual(response.json()["case"]["diagnosis"], "Updated diagnosis")
        self.assertTrue(
            CaseActivityLog.objects.filter(
                case=case,
                event_type=ActivityEventType.SYSTEM,
                note__icontains="Diagnosis updated",
            ).exists()
        )
        self.assertTrue(
            CaseActivityLog.objects.filter(
                case=case,
                event_type=ActivityEventType.NOTE,
                note="Updated note",
            ).exists()
        )

    def test_recent_case_update_no_op_does_not_add_logs(self):
        self.client.force_login(self.user)
        case = self.create_recent_case(diagnosis="Stable diagnosis", notes="Stable note")
        initial_log_count = case.activity_logs.count()

        response = self.client.post(
            reverse("patients:recent_case_update", kwargs={"pk": case.pk}),
            {"diagnosis": "Stable diagnosis", "notes": "Stable note"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "No changes to save.")
        self.assertEqual(case.activity_logs.count(), initial_log_count)

    def test_recent_case_update_notes_only_keeps_blank_diagnosis_blank(self):
        self.client.force_login(self.user)
        case = self.create_recent_case(diagnosis="", notes="")

        response = self.client.post(
            reverse("patients:recent_case_update", kwargs={"pk": case.pk}),
            {"diagnosis": "", "notes": "Dashboard note only"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        case.refresh_from_db()
        self.assertEqual(case.diagnosis, "")
        self.assertEqual(case.notes, "Dashboard note only")

    def test_reception_can_view_recent_cases_but_cannot_mutate(self):
        self.login_as_role("Reception", username="reception_recent_write")
        case = self.create_recent_case(diagnosis="Reception case", notes="Read only note")
        task = Task.objects.create(
            case=case,
            title="Read-only task",
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        recent_response = self.client.get(
            reverse("patients:recent_cases"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        case_update_response = self.client.post(
            reverse("patients:recent_case_update", kwargs={"pk": case.pk}),
            {"diagnosis": "Blocked", "notes": "Blocked"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        task_update_response = self.client.post(
            reverse("patients:task_quick_note", kwargs={"pk": task.pk}),
            {"note": "Blocked task change"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(recent_response.status_code, 200)
        self.assertFalse(recent_response.json()["results"][0]["can_edit"])
        self.assertEqual(case_update_response.status_code, 403)
        self.assertEqual(task_update_response.status_code, 403)

    def test_add_call_log_requires_associated_task(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-ACTION-06",
            first_name="Call",
            last_name="Validation",
            phone_number="9876505666",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_call_create", kwargs={"pk": case.id}),
            {"task": "", "outcome": CallOutcome.NO_ANSWER, "notes": "Missing task"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CallLog.objects.filter(case=case, notes="Missing task").exists())

    def test_case_list_and_case_detail_render_theme_category_chip_and_real_status_classes(self):
        self.client.force_login(self.user)
        self.surgery.theme_bg_color = "#abcdef"
        self.surgery.theme_text_color = "#123456"
        self.surgery.save()
        today = timezone.localdate()

        active_case = Case.objects.create(
            uhid="UH-THEME-ACTIVE",
            first_name="Theme",
            last_name="Active",
            phone_number="9876504450",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=today + timedelta(days=10),
            created_by=self.user,
        )
        loss_case = Case.objects.create(
            uhid="UH-THEME-LTFU",
            first_name="Theme",
            last_name="Lost",
            phone_number="9876504451",
            category=self.surgery,
            status=CaseStatus.LOSS_TO_FOLLOW_UP,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=today + timedelta(days=12),
            created_by=self.user,
        )

        case_list_response = self.client.get(reverse("patients:case_list"))
        active_detail_response = self.client.get(reverse("patients:case_detail", kwargs={"pk": active_case.pk}))
        loss_detail_response = self.client.get(reverse("patients:case_detail", kwargs={"pk": loss_case.pk}))

        self.assertEqual(case_list_response.status_code, 200)
        self.assertContains(case_list_response, "theme-category-chip")
        self.assertContains(case_list_response, "--theme-category-bg: #abcdef;")
        self.assertContains(active_detail_response, "case-detail-status-pill--active")
        self.assertContains(active_detail_response, "--theme-category-bg: #abcdef;")
        self.assertContains(loss_detail_response, "case-detail-status-pill--loss-to-follow-up")

    def test_case_detail_includes_case_header_theme_variable_from_theme_settings(self):
        self.client.force_login(self.user)
        today = timezone.localdate()
        case = Case.objects.create(
            uhid="UH-THEME-HEADER",
            first_name="Theme",
            last_name="Header",
            phone_number="9876504460",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=today + timedelta(days=7),
            created_by=self.user,
        )
        theme_settings = ThemeSettings.get_solo()
        theme_settings.tokens = {
            "nav": {"bg": "#123456"},
            "case_header": {"bg": "#654321"},
        }
        theme_settings.save()

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "--theme-nav-bg: #123456;")
        self.assertContains(response, "--theme-case-header-bg: #654321;")
        self.assertContains(response, 'data-testid="case-detail-hero"')

    def test_dashboard_week_navigation_invalid_and_negative_offsets_clamp_to_this_week(self):
        self.client.force_login(self.user)

        invalid_response = self.client.get(reverse("patients:dashboard"), {"week_offset": "invalid"})
        negative_response = self.client.get(reverse("patients:dashboard"), {"week_offset": -3})

        current_week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        current_week_end = current_week_start + timedelta(days=6)

        self.assertEqual(invalid_response.status_code, 200)
        self.assertEqual(invalid_response.context["week_offset"], 0)
        self.assertFalse(invalid_response.context["show_previous_week"])
        self.assertEqual(invalid_response.context["selected_week_start"], current_week_start)
        self.assertEqual(invalid_response.context["selected_week_end"], current_week_end)

        self.assertEqual(negative_response.status_code, 200)
        self.assertEqual(negative_response.context["week_offset"], 0)
        self.assertFalse(negative_response.context["show_previous_week"])
        self.assertEqual(negative_response.context["selected_week_start"], current_week_start)
        self.assertEqual(negative_response.context["selected_week_end"], current_week_end)

    def test_dashboard_upcoming_schedule_renders_this_week_default(self):
        self.client.force_login(self.user)
        today = timezone.localdate()
        current_week_start = today - timedelta(days=today.weekday())
        current_week_end = current_week_start + timedelta(days=6)
        today_index = (today - current_week_start).days
        next_week_start = current_week_start + timedelta(days=7)
        schedule_case = Case.objects.create(
            uhid="UH-SCHED-001",
            first_name="Today",
            last_name="Patient",
            phone_number="9876504001",
            category=self.surgery,
            subcategory=CaseSubcategory.GENERAL_SURGERY,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=today + timedelta(days=2),
            created_by=self.user,
        )
        Task.objects.create(case=schedule_case, title="Today review", due_date=today, created_by=self.user)
        Task.objects.create(
            case=schedule_case,
            title="Next week review",
            due_date=next_week_start + timedelta(days=2),
            created_by=self.user,
        )
        Task.objects.create(
            case=schedule_case,
            title="Awaiting",
            due_date=today + timedelta(days=1),
            status=TaskStatus.AWAITING_REPORTS,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        schedule_days = response.context["appointment_schedule_days"]
        self.assertEqual(response.context["week_offset"], 0)
        self.assertFalse(response.context["show_previous_week"])
        self.assertEqual(response.context["selected_week_start"], current_week_start)
        self.assertEqual(response.context["selected_week_end"], current_week_end)
        self.assertEqual(len(schedule_days), 7)
        self.assertEqual(schedule_days[0]["date"], current_week_start)
        self.assertEqual(schedule_days[-1]["date"], current_week_end)
        self.assertTrue(schedule_days[today_index]["is_selected"])
        self.assertEqual(schedule_days[today_index]["count"], 1)
        self.assertContains(response, "This week")
        self.assertContains(response, "Next week")
        self.assertNotContains(response, "Previous week")
        self.assertContains(response, 'href="?week_offset=0" data-upcoming-week-link')
        self.assertContains(response, 'href="?week_offset=1" data-upcoming-week-link')
        self.assertContains(response, 'data-upcoming-day-trigger=', count=7)
        self.assertContains(response, 'data-upcoming-day-panel=', count=7)
        self.assertContains(response, 'data-upcoming-schedule')
        self.assertContains(response, "Today review")
        self.assertNotContains(response, "Next week review")
        self.assertContains(response, "Open case")
        self.assertContains(response, schedule_case.get_subcategory_display())
        self.assertNotContains(response, 'class="upcoming-schedule-row" href=')
        empty_label = f"No scheduled patients for {(current_week_start + timedelta(days=1)).strftime('%B')} {(current_week_start + timedelta(days=1)).day}."
        self.assertContains(response, empty_label)

    def test_dashboard_upcoming_schedule_shows_next_week_only_with_previous_control(self):
        self.client.force_login(self.user)
        today = timezone.localdate()
        current_week_start = today - timedelta(days=today.weekday())
        next_week_start = current_week_start + timedelta(days=7)
        next_week_end = next_week_start + timedelta(days=6)
        next_week_task_date = next_week_start + timedelta(days=2)
        this_week_case = Case.objects.create(
            uhid="UH-SCHED-THIS",
            first_name="This",
            last_name="Week",
            phone_number="9876504005",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=current_week_start + timedelta(days=2),
            created_by=self.user,
        )
        next_week_case = Case.objects.create(
            uhid="UH-SCHED-NEXT",
            first_name="Next",
            last_name="Week",
            phone_number="9876504006",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=next_week_task_date,
            created_by=self.user,
        )
        Task.objects.create(case=this_week_case, title="Current week review", due_date=current_week_start + timedelta(days=2), created_by=self.user)
        Task.objects.create(case=next_week_case, title="Next week review", due_date=next_week_task_date, created_by=self.user)

        response = self.client.get(reverse("patients:dashboard"), {"week_offset": 1})

        self.assertEqual(response.status_code, 200)
        schedule_days = response.context["appointment_schedule_days"]
        self.assertEqual(response.context["week_offset"], 1)
        self.assertTrue(response.context["show_previous_week"])
        self.assertEqual(response.context["previous_week_offset"], 0)
        self.assertEqual(response.context["next_week_offset"], 2)
        self.assertEqual(response.context["selected_week_start"], next_week_start)
        self.assertEqual(response.context["selected_week_end"], next_week_end)
        self.assertEqual(len(schedule_days), 7)
        self.assertEqual(schedule_days[0]["date"], next_week_start)
        self.assertEqual(schedule_days[-1]["date"], next_week_end)
        self.assertTrue(schedule_days[0]["is_selected"])
        self.assertContains(response, "Previous week")
        self.assertContains(response, "This week")
        self.assertContains(response, "Next week")
        self.assertContains(response, 'href="?week_offset=0" data-upcoming-week-link', count=2)
        self.assertContains(response, 'href="?week_offset=2" data-upcoming-week-link')
        content = response.content.decode()
        rendered_titles = [title for day in schedule_days for row in day["rows"] for title in row["task_titles"]]
        self.assertLess(content.index("Previous week"), content.index("This week"))
        self.assertIn("Next week review", rendered_titles)
        self.assertNotIn("Current week review", rendered_titles)

    def test_dashboard_upcoming_schedule_groups_rows_and_deduplicates_category_dots(self):
        self.client.force_login(self.user)
        today = timezone.localdate()
        current_week_start = today - timedelta(days=today.weekday())
        next_week_start = current_week_start + timedelta(days=7)
        target_date = next_week_start + timedelta(days=2)
        anc_case = Case.objects.create(
            uhid="UH-SCHED-ANC",
            first_name="Asha",
            last_name="ANC",
            phone_number="9876504002",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=today - timedelta(days=70),
            edd=today + timedelta(days=200),
            created_by=self.user,
        )
        surgery_case = Case.objects.create(
            uhid="UH-SCHED-SURG",
            first_name="Grouped",
            last_name="Surgery",
            phone_number="9876504003",
            category=self.surgery,
            subcategory=CaseSubcategory.ORTHOPEDICS,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=target_date,
            created_by=self.user,
        )
        Task.objects.create(case=anc_case, title="ANC Review", due_date=target_date, created_by=self.user)
        Task.objects.create(case=surgery_case, title="Lab", due_date=target_date, created_by=self.user)
        Task.objects.create(case=surgery_case, title="ECG", due_date=target_date, created_by=self.user)
        Task.objects.create(case=surgery_case, title="ECG", due_date=target_date, created_by=self.user)

        response = self.client.get(reverse("patients:dashboard"), {"week_offset": 1})

        self.assertEqual(response.status_code, 200)
        schedule_day = next(day for day in response.context["appointment_schedule_days"] if day["date"] == target_date)
        self.assertEqual(response.context["week_offset"], 1)
        self.assertEqual(schedule_day["count"], 2)
        self.assertEqual([category["name"] for category in schedule_day["categories"]], ["ANC", "Surgery"])
        self.assertEqual([subcategory["label"] for subcategory in schedule_day["subcategories"]], [surgery_case.get_subcategory_display()])
        grouped_row = next(row for row in schedule_day["rows"] if row["patient_name"] == "Grouped Surgery")
        self.assertEqual(grouped_row["task_titles"], ["Lab", "ECG"])
        self.assertEqual(grouped_row["subcategory_name"], surgery_case.get_subcategory_display())
        self.assertContains(response, 'title="ANC"')
        self.assertContains(response, 'title="Surgery"')
        self.assertContains(response, surgery_case.get_subcategory_display())

    def test_dashboard_upcoming_schedule_uses_category_theme_colors_for_dots_and_rows(self):
        self.client.force_login(self.user)
        today = timezone.localdate()
        current_week_start = today - timedelta(days=today.weekday())
        next_week_start = current_week_start + timedelta(days=7)
        self.surgery.theme_bg_color = "#abcdef"
        self.surgery.theme_text_color = "#123456"
        self.surgery.save()
        case = Case.objects.create(
            uhid="UH-SCHED-COLOR",
            first_name="Color",
            last_name="Patient",
            phone_number="9876504004",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=next_week_start + timedelta(days=3),
            created_by=self.user,
        )
        Task.objects.create(case=case, title="Theme review", due_date=next_week_start + timedelta(days=1), created_by=self.user)

        response = self.client.get(reverse("patients:dashboard"), {"week_offset": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["week_offset"], 1)
        self.assertContains(response, "--schedule-dot-ring: #abcdef;")
        self.assertContains(response, f"--schedule-dot-fill: {mix_colors('#123456', '#abcdef', 0.22)};")
        self.assertContains(response, "--upcoming-category-bg: #abcdef; --upcoming-category-text: #123456;")


    def test_case_form_bootstraps_categories_when_empty(self):
        DepartmentConfig.objects.all().delete()
        self.client.force_login(self.user)
        response = self.client.get(reverse("patients:case_create"))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(DepartmentConfig.objects.count(), 3)

    def test_case_create_page_renders_preview_shell_and_default_workflow_state(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:case_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Show Help")
        self.assertContains(response, 'id="case-create-preview-sync"')
        self.assertContains(response, reverse("patients:case_create_preview"))
        self.assertContains(response, reverse("patients:case_create_identity_check"))
        self.assertContains(response, 'id="case-create-shell-state" data-workflow-key="generic"')
        self.assertContains(response, 'name="prefix"')
        self.assertContains(response, 'name="status"')
        self.assertContains(response, 'id="id_status"')
        self.assertNotContains(response, '<label for="id_status">')
        self.assertContains(response, "case-create-choice-grid")
        self.assertContains(response, "case-create-choice")
        self.assertContains(response, "case-create-gender-field")
        self.assertGreater(len(list(response.context["form"]["category"])), 0)
        self.assertNotContains(response, '<select name="category"')

    def test_case_create_invalid_submission_includes_inline_validation_hooks(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "",
                "first_name": "",
                "last_name": "",
                "phone_number": "",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid-feedback")
        self.assertContains(response, "This field is required.")
        self.assertContains(response, "case-create-field")

    def test_case_create_defaults_status_to_active_when_not_submitted(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH-DEFAULT-STATUS",
                "prefix": CasePrefix.MR,
                "first_name": "Default",
                "last_name": "Status",
                "phone_number": "9876500459",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "age": "32",
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": (timezone.localdate() + timedelta(days=9)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        created_case = Case.objects.get(uhid="UH-DEFAULT-STATUS")
        self.assertEqual(created_case.status, CaseStatus.ACTIVE)

    def test_case_create_defaults_anc_gender_to_female_when_not_submitted(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH-ANC-FEMALE",
                "prefix": CasePrefix.MRS,
                "first_name": "Anc",
                "last_name": "Default",
                "phone_number": "9876500460",
                "category": self.anc.id,
                "age": "25",
                "lmp": (timezone.localdate() - timedelta(days=42)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=238)).isoformat(),
                "rch_bypass": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        created_case = Case.objects.get(uhid="UH-ANC-FEMALE")
        self.assertEqual(created_case.gender, Gender.FEMALE)
        self.assertIsNone(created_case.gravida)
        self.assertIsNone(created_case.para)
        self.assertIsNone(created_case.abortions)
        self.assertIsNone(created_case.living)

    def test_case_create_persists_explicit_zero_gpla_values_for_anc(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH-ANC-ZERO-GPLA",
                "prefix": CasePrefix.MS,
                "first_name": "Anc",
                "last_name": "Zero",
                "phone_number": "9876500461",
                "category": self.anc.id,
                "age": "24",
                "lmp": (timezone.localdate() - timedelta(days=49)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=231)).isoformat(),
                "rch_bypass": "on",
                "gravida": "0",
                "para": "0",
                "abortions": "0",
                "living": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        created_case = Case.objects.get(uhid="UH-ANC-ZERO-GPLA")
        self.assertEqual(created_case.gravida, 0)
        self.assertEqual(created_case.para, 0)
        self.assertEqual(created_case.abortions, 0)
        self.assertEqual(created_case.living, 0)

    def test_case_create_invalid_anc_gpla_submission_shows_inline_error(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH-ANC-GPLA-INVALID",
                "prefix": CasePrefix.MS,
                "first_name": "Anc",
                "last_name": "Invalid",
                "phone_number": "9876500462",
                "category": self.anc.id,
                "age": "28",
                "lmp": (timezone.localdate() - timedelta(days=56)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=224)).isoformat(),
                "rch_bypass": "on",
                "gravida": "1",
                "para": "2",
                "abortions": "0",
                "living": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "P cannot exceed G.")
        self.assertContains(response, "data-gpla-counter")

    def test_case_create_invalid_anc_zero_gpla_submission_shows_inline_error(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH-ANC-GPLA-ZERO-INVALID",
                "prefix": CasePrefix.MRS,
                "first_name": "Anc",
                "last_name": "ZeroInvalid",
                "phone_number": "9876500463",
                "category": self.anc.id,
                "age": "29",
                "lmp": (timezone.localdate() - timedelta(days=63)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=217)).isoformat(),
                "rch_bypass": "on",
                "gravida": "0",
                "para": "0",
                "abortions": "1",
                "living": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "P + A cannot exceed G.")
        self.assertContains(response, "data-gpla-counter")
        self.assertFalse(Case.objects.filter(uhid="UH-ANC-GPLA-ZERO-INVALID").exists())

    def test_case_create_duplicate_active_uhid_returns_inline_error(self):
        Case.objects.create(
            uhid="UH-DUPLICATE",
            first_name="Existing",
            last_name="Case",
            phone_number="9876500450",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH-DUPLICATE",
                "prefix": CasePrefix.MR,
                "first_name": "New",
                "last_name": "Case",
                "phone_number": "9876500451",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "age": "29",
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": (timezone.localdate() + timedelta(days=11)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No duplicate active cases are allowed for the same UHID.")

    def test_case_create_invalid_phone_numbers_return_inline_error(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH-PHONE-INVALID",
                "prefix": CasePrefix.MR,
                "first_name": "Phone",
                "last_name": "Invalid",
                "phone_number": "12345",
                "alternate_phone_number": "abc",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "age": "41",
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": (timezone.localdate() + timedelta(days=8)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Phone number must be exactly 10 digits.")
        self.assertContains(response, "Alternate phone number must be exactly 10 digits.")


    def test_admin_settings_page_access_and_summary_links(self):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Management")
        self.assertContains(response, "Categories & Workflow")
        self.assertContains(response, reverse("patients:settings_user_management"))
        self.assertContains(response, reverse("patients:settings_categories"))
        self.assertContains(response, reverse("patients:settings_database"))
        self.assertContains(response, reverse("patients:settings_device_access"))
        self.assertContains(response, reverse("patients:settings_theme"))
        self.assertContains(response, reverse("patients:settings_seed_mock_data"))
        self.assertContains(response, reverse("patients:changelog"))

    def test_admin_settings_page_shows_changelog_link(self):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("patients:changelog"))

    def test_admin_settings_page_handles_missing_settings_schema_gracefully(self):
        self.login_as_admin()

        with patch(
            "patients.views.DeviceApprovalPolicy.get_solo",
            side_effect=ProgrammingError('relation "patients_deviceapprovalpolicy" does not exist'),
        ):
            response = self.client.get(reverse("patients:settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Some settings modules are unavailable on this server.")
        self.assertContains(response, "Run python manage.py migrate on the VPS and reload this page.")
        self.assertContains(
            response,
            "Device access data is unavailable until database migrations are applied on this server.",
        )
        self.assertContains(response, "Run Migrations First")

    def test_admin_settings_page_handles_legacy_theme_tokens_missing_new_fields(self):
        self.login_as_admin()
        theme_settings = ThemeSettings.get_solo()
        legacy_tokens = deepcopy(merge_theme_tokens(theme_settings.tokens))
        legacy_tokens["buttons"].pop("success", None)
        ThemeSettings.objects.filter(pk=theme_settings.pk).update(tokens=legacy_tokens)

        response = self.client.get(reverse("patients:settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Theme settings are currently using defaults.")
        self.assertNotContains(response, "Some settings modules are unavailable on this server.")

    def test_admin_settings_page_shows_theme_link_and_theme_page_requires_manage_settings(self):
        self.client.force_login(self.user)

        forbidden_get = self.client.get(reverse("patients:settings_theme"))
        forbidden_post = self.client.post(reverse("patients:settings_theme"), {"action": "restore_defaults"})

        self.assertEqual(forbidden_get.status_code, 403)
        self.assertEqual(forbidden_post.status_code, 403)

        self.login_as_admin()
        settings_response = self.client.get(reverse("patients:settings"))
        theme_response = self.client.get(reverse("patients:settings_theme"))

        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, reverse("patients:settings_theme"))
        self.assertEqual(theme_response.status_code, 200)
        anc = DepartmentConfig.objects.get(name="ANC")
        self.assertContains(theme_response, "Theme Settings")
        self.assertContains(theme_response, "Success Button")
        self.assertContains(theme_response, "buttons__success__bg")
        self.assertContains(theme_response, "Blood Pressure Chart")
        self.assertContains(theme_response, "vitals_chart__blood_pressure")
        self.assertContains(theme_response, "Female Tag")
        self.assertContains(theme_response, "search__gender_female__bg")
        self.assertContains(theme_response, "Male Tag")
        self.assertContains(theme_response, "search__gender_male__bg")
        self.assertContains(theme_response, "Other Tag")
        self.assertContains(theme_response, "search__gender_other__bg")
        self.assertContains(theme_response, "Categories")
        self.assertContains(theme_response, anc.name)
        self.assertContains(theme_response, f"theme-category-{anc.pk}-preview")
        self.assertContains(theme_response, "Vitals Module")
        self.assertContains(theme_response, "NNH Preview")
        self.assertContains(theme_response, "Quick Entry")
        self.assertContains(theme_response, "New Case")
        self.assertContains(theme_response, "Filter categories preview")
        self.assertContains(theme_response, "global-search-filter-panel")
        self.assertNotContains(theme_response, "bp-systolic")

    def test_admin_settings_subpages_show_theme_link(self):
        self.login_as_admin()
        theme_url = reverse("patients:settings_theme")
        settings_pages = [
            "patients:settings_case_management",
            "patients:settings_categories",
            "patients:settings_database",
            "patients:settings_device_access",
            "patients:settings_seed_mock_data",
            "patients:settings_user_management",
            "patients:changelog",
        ]

        for route_name in settings_pages:
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, theme_url)

    def test_admin_settings_page_shows_device_access_link_and_page_requires_manage_settings(self):
        pending_user = get_user_model().objects.create_user(username="pilot-target", password="strong-password-123")
        pending_device = self.create_device_credential(
            user=pending_user,
            status=StaffDeviceCredentialStatus.PENDING,
            credential_id="pending-device",
            device_label="Pilot browser",
        )

        self.client.force_login(self.user)
        forbidden_get = self.client.get(reverse("patients:settings_device_access"))
        forbidden_post = self.client.post(
            reverse("patients:settings_device_access"),
            {"action": "revoke_device", "credential_id": pending_device.pk},
        )

        self.assertEqual(forbidden_get.status_code, 403)
        self.assertEqual(forbidden_post.status_code, 403)

        self.login_as_admin()
        settings_response = self.client.get(reverse("patients:settings"))
        device_response = self.client.get(reverse("patients:settings_device_access"))

        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, reverse("patients:settings_device_access"))
        self.assertEqual(device_response.status_code, 200)
        self.assertContains(device_response, "Device Access")

    def test_admin_settings_page_shows_categories_link_and_page_requires_manage_settings(self):
        self.client.force_login(self.user)

        forbidden_get = self.client.get(reverse("patients:settings_categories"))
        forbidden_post = self.client.post(
            reverse("patients:settings_categories"),
            {"action": "create_category", "name": "Blocked"},
        )

        self.assertEqual(forbidden_get.status_code, 403)
        self.assertEqual(forbidden_post.status_code, 403)

        self.login_as_admin()
        settings_response = self.client.get(reverse("patients:settings"))
        categories_response = self.client.get(reverse("patients:settings_categories"))

        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, reverse("patients:settings_categories"))
        self.assertEqual(categories_response.status_code, 200)
        self.assertContains(categories_response, "Categories & Workflow")
        self.assertContains(categories_response, "does not alter live task generation today")

    def test_admin_settings_page_shows_user_management_link_and_page_requires_manage_settings(self):
        self.client.force_login(self.user)

        forbidden_get = self.client.get(reverse("patients:settings_user_management"))
        forbidden_post = self.client.post(
            reverse("patients:settings_user_management"),
            {
                "action": "clear_temp_password_note",
                "user_id": str(self.user.pk),
            },
        )

        self.assertEqual(forbidden_get.status_code, 403)
        self.assertEqual(forbidden_post.status_code, 403)

        self.login_as_admin()
        settings_response = self.client.get(reverse("patients:settings"))
        user_management_response = self.client.get(reverse("patients:settings_user_management"))

        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, reverse("patients:settings_user_management"))
        self.assertEqual(user_management_response.status_code, 200)
        self.assertContains(user_management_response, "Create User")
        self.assertContains(user_management_response, "Edit User")
        self.assertContains(user_management_response, "Roles")

    def test_user_management_page_can_create_user_with_role(self):
        self.login_as_admin()
        reception_group, _ = Group.objects.get_or_create(name="Reception")

        response = self.client.post(
            reverse("patients:settings_user_management"),
            {
                "action": "create_user",
                "first_name": "Anita",
                "last_name": "Thomas",
                "username": "frontdesk",
                "password1": "strong-password-456",
                "password2": "strong-password-456",
                "role": str(reception_group.pk),
                "is_active": "on",
                "temporary_password_note": "Temp password: strong-password-456",
                "selected_user_id": str(self.user.pk),
                "tab": "users",
            },
        )

        self.assertEqual(response.status_code, 302)
        created_user = get_user_model().objects.get(username="frontdesk")
        self.assertEqual(created_user.first_name, "Anita")
        self.assertEqual(created_user.last_name, "Thomas")
        self.assertTrue(created_user.is_active)
        self.assertEqual(list(created_user.groups.values_list("name", flat=True)), ["Reception"])
        self.assertTrue(created_user.check_password("strong-password-456"))
        self.assertEqual(created_user.admin_note.temporary_password_note, "Temp password: strong-password-456")

    def test_user_management_page_can_update_existing_user_details_role_and_password(self):
        target_user = get_user_model().objects.create_user(
            username="caller-user",
            password="strong-password-123",
            first_name="Caller",
            last_name="User",
        )
        caller_group, _ = Group.objects.get_or_create(name="Caller")
        doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        target_user.groups.add(caller_group)

        self.login_as_admin()

        response = self.client.post(
            reverse("patients:settings_user_management"),
            {
                "action": "update_user",
                "user_id": str(target_user.pk),
                "first_name": "Updated",
                "last_name": "Doctor",
                "username": "doctor-user",
                "password1": "new-strong-password-789",
                "password2": "new-strong-password-789",
                "role": str(doctor_group.pk),
                "is_active": "on",
                "temporary_password_note": "Handed off on paper",
                "tab": "users",
            },
        )

        self.assertEqual(response.status_code, 302)
        target_user.refresh_from_db()
        self.assertEqual(target_user.first_name, "Updated")
        self.assertEqual(target_user.last_name, "Doctor")
        self.assertEqual(target_user.username, "doctor-user")
        self.assertTrue(target_user.is_active)
        self.assertEqual(list(target_user.groups.values_list("name", flat=True)), ["Doctor"])
        self.assertTrue(target_user.check_password("new-strong-password-789"))
        self.assertEqual(target_user.admin_note.temporary_password_note, "Handed off on paper")

    def test_user_management_page_can_clear_temporary_password_note(self):
        target_user = get_user_model().objects.create_user(username="noted-user", password="strong-password-123")
        UserAdminNote.objects.create(
            user=target_user,
            temporary_password_note="Temporary credential",
            updated_by=self.user,
        )

        self.login_as_admin()

        response = self.client.post(
            reverse("patients:settings_user_management"),
            {
                "action": "clear_temp_password_note",
                "user_id": str(target_user.pk),
                "tab": "users",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        target_user.admin_note.refresh_from_db()
        self.assertEqual(target_user.admin_note.temporary_password_note, "")
        self.assertContains(response, "Cleared the temporary password note")

    def test_user_management_roles_tab_can_create_role(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("patients:settings_user_management"),
            {
                "action": "create_role",
                "tab": "roles",
                "role_name": "Coordinator",
                "can_case_create": "on",
                "can_case_edit": "on",
                "can_note_add": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(RoleSetting.objects.filter(role_name="Coordinator", can_case_create=True, can_note_add=True).exists())
        self.assertTrue(Group.objects.filter(name="Coordinator").exists())
        self.assertContains(response, "Created role Coordinator.")

    def test_user_management_roles_tab_can_update_role_permissions(self):
        self.login_as_admin()
        role = RoleSetting.objects.get(role_name="Doctor")

        response = self.client.post(
            reverse("patients:settings_user_management"),
            {
                "action": "update_role",
                "tab": "roles",
                "role_id": str(role.pk),
                "can_case_create": "on",
                "can_case_edit": "on",
                "can_task_create": "on",
                "can_task_edit": "on",
                "can_note_add": "on",
                "can_manage_settings": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        role.refresh_from_db()
        self.assertTrue(role.can_manage_settings)
        self.assertContains(response, "Updated permissions for Doctor.")

    def test_user_management_page_blocks_removing_last_settings_admin(self):
        self.login_as_admin()
        doctor_group, _ = Group.objects.get_or_create(name="Doctor")

        response = self.client.post(
            reverse("patients:settings_user_management"),
            {
                "action": "update_user",
                "user_id": str(self.user.pk),
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "username": self.user.username,
                "role": str(doctor_group.pk),
                "is_active": "on",
                "tab": "users",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(list(self.user.groups.values_list("name", flat=True)), ["Admin"])
        self.assertContains(response, "Keep at least one active admin user with settings access.")

    def test_categories_settings_page_can_create_category(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("patients:settings_categories"),
            {
                "action": "create_category",
                "name": "Postpartum",
                "auto_follow_up_days": "21",
                "predefined_actions_text": "Review, Counseling",
                "metadata_template_text": '{"visit_type": "String"}',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        category = DepartmentConfig.objects.get(name="Postpartum")
        self.assertEqual(category.auto_follow_up_days, 21)
        self.assertEqual(category.predefined_actions, ["Review", "Counseling"])
        self.assertEqual(category.metadata_template, {"visit_type": "String"})
        self.assertContains(response, "Saved category Postpartum.")

    def test_categories_settings_page_can_update_category(self):
        self.login_as_admin()
        category = DepartmentConfig.objects.get(name="ANC")

        response = self.client.post(
            reverse("patients:settings_categories"),
            {
                "action": "update_category",
                "category_id": str(category.pk),
                "name": "ANC",
                "auto_follow_up_days": "14",
                "predefined_actions_text": "ANC Visit, BP Check",
                "metadata_template_text": '{"lmp": "Date", "risk_band": "String"}',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.auto_follow_up_days, 14)
        self.assertEqual(category.predefined_actions, ["ANC Visit", "BP Check"])
        self.assertEqual(category.metadata_template, {"lmp": "Date", "risk_band": "String"})
        self.assertContains(response, "Updated category ANC.")

    def test_admin_settings_page_shows_database_link_and_page_requires_manage_settings(self):
        self.client.force_login(self.user)

        forbidden_get = self.client.get(reverse("patients:settings_database"))
        forbidden_post = self.client.post(reverse("patients:settings_database"), {"action": "backup"})

        self.assertEqual(forbidden_get.status_code, 403)
        self.assertEqual(forbidden_post.status_code, 403)

        self.login_as_admin()
        settings_response = self.client.get(reverse("patients:settings"))
        database_response = self.client.get(reverse("patients:settings_database"))

        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, reverse("patients:settings_database"))
        self.assertEqual(database_response.status_code, 200)
        self.assertContains(database_response, "Database Management")
        self.assertContains(database_response, database_bundle.IMPORT_CONFIRMATION_PHRASE)
        self.assertContains(database_response, "Automatic backup scheduler")

    def test_admin_settings_page_shows_case_management_link_and_page_requires_manage_settings(self):
        target_case = self.create_bundle_case(uhid="UH-CASE-MGMT-001", phone_number="9000000191")

        self.client.force_login(self.user)
        forbidden_get = self.client.get(reverse("patients:settings_case_management"))
        forbidden_post = self.client.post(
            reverse("patients:settings_case_management"),
            {"action": "request_delete", "case_id": str(target_case.pk)},
        )

        self.assertEqual(forbidden_get.status_code, 403)
        self.assertEqual(forbidden_post.status_code, 403)

        self.login_as_admin()
        settings_response = self.client.get(reverse("patients:settings"))
        case_management_response = self.client.get(reverse("patients:settings_case_management"))

        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, reverse("patients:settings_case_management"))
        self.assertEqual(case_management_response.status_code, 200)
        self.assertContains(case_management_response, "Case Management")
        self.assertContains(case_management_response, "Archive")
        self.assertContains(case_management_response, "Permanent delete")
        self.assertContains(case_management_response, "UH-CASE-MGMT-001")

    def test_case_management_page_search_filters_cases(self):
        self.create_bundle_case(
            uhid="UH-CASE-SEARCH-001",
            first_name="Unique",
            last_name="Target",
            phone_number="9000000192",
        )
        self.create_bundle_case(
            uhid="UH-CASE-SEARCH-002",
            first_name="Other",
            last_name="Patient",
            phone_number="9000000193",
        )
        self.login_as_admin()

        response = self.client.get(reverse("patients:settings_case_management"), {"q": "Unique"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "UH-CASE-SEARCH-001")
        self.assertNotContains(response, "UH-CASE-SEARCH-002")
        self.assertContains(response, "Found 1 matching case")

    def test_case_management_delete_requires_confirmation_and_removes_linked_records(self):
        target_case = self.create_bundle_case(uhid="UH-CASE-DELETE-001", phone_number="9000000194")
        other_case = self.create_bundle_case(uhid="UH-CASE-DELETE-002", phone_number="9000000195")
        task = Task.objects.create(
            case=target_case,
            title="Delete review",
            due_date=timezone.localdate(),
            created_by=self.user,
        )
        VitalEntry.objects.create(
            case=target_case,
            recorded_at=timezone.now(),
            pr=72,
            created_by=self.user,
            updated_by=self.user,
        )
        CaseActivityLog.objects.create(case=target_case, task=task, user=self.user, note="Delete me")
        CallLog.objects.create(case=target_case, task=task, outcome=CallOutcome.NO_ANSWER, notes="Delete me", staff_user=self.user)

        self.login_as_admin()

        direct_delete_response = self.client.post(
            reverse("patients:settings_case_management"),
            {"action": "delete_case", "case_id": str(target_case.pk)},
            follow=True,
        )

        self.assertEqual(direct_delete_response.status_code, 200)
        self.assertTrue(Case.objects.filter(pk=target_case.pk).exists())
        self.assertContains(direct_delete_response, "Please review the confirmation panel before deleting a case.")

        confirm_response = self.client.post(
            reverse("patients:settings_case_management"),
            {"action": "request_delete", "case_id": str(target_case.pk)},
            follow=True,
        )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertContains(confirm_response, "Confirm permanent delete")
        self.assertContains(confirm_response, "UH-CASE-DELETE-001")
        self.assertContains(confirm_response, "1 task")
        self.assertContains(confirm_response, "1 vital entry")
        self.assertContains(confirm_response, "1 call log")
        self.assertContains(confirm_response, "1 activity log")

        delete_response = self.client.post(
            reverse("patients:settings_case_management"),
            {"action": "delete_case", "case_id": str(target_case.pk)},
            follow=True,
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(Case.objects.filter(pk=target_case.pk).exists())
        self.assertTrue(Case.objects.filter(pk=other_case.pk).exists())
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())
        self.assertFalse(VitalEntry.objects.filter(case_id=target_case.pk).exists())
        self.assertFalse(CaseActivityLog.objects.filter(case_id=target_case.pk).exists())
        self.assertFalse(CallLog.objects.filter(case_id=target_case.pk).exists())
        self.assertContains(delete_response, "Deleted case UH-CASE-DELETE-001")

    def test_case_management_archive_hides_case_from_daily_views_but_keeps_record(self):
        archived_case = self.create_bundle_case(
            uhid="UH-CASE-ARCHIVE-001",
            first_name="Archive",
            last_name="Hidden",
            phone_number="9000000196",
            diagnosis="Archive target",
        )
        visible_case = self.create_bundle_case(
            uhid="UH-CASE-ARCHIVE-002",
            first_name="Visible",
            last_name="Patient",
            phone_number="9000000197",
            diagnosis="Visible target",
        )
        Task.objects.create(
            case=archived_case,
            title="Archive task",
            due_date=timezone.localdate(),
            created_by=self.user,
        )
        Task.objects.create(
            case=visible_case,
            title="Visible task",
            due_date=timezone.localdate(),
            created_by=self.user,
        )

        self.login_as_admin()
        response = self.client.post(
            reverse("patients:settings_case_management"),
            {"action": "archive_case", "case_id": str(archived_case.pk)},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        archived_case.refresh_from_db()
        self.assertTrue(archived_case.is_archived)
        self.assertContains(response, "Archived case UH-CASE-ARCHIVE-001")
        self.assertContains(response, "Archived")

        case_list_response = self.client.get(reverse("patients:case_list"))
        self.assertEqual(case_list_response.status_code, 200)
        self.assertNotContains(case_list_response, "UH-CASE-ARCHIVE-001")
        self.assertContains(case_list_response, "UH-CASE-ARCHIVE-002")

        dashboard_response = self.client.get(reverse("patients:dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        today_case_ids = {card["case_id"] for card in dashboard_response.context["today_cards"]}
        self.assertNotIn(archived_case.pk, today_case_ids)
        self.assertIn(visible_case.pk, today_case_ids)

        search_response = self.client.get(reverse("patients:universal_case_search"), {"q": "Archive target"})
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()["results"], [])

        detail_response = self.client.get(reverse("patients:case_detail", args=[archived_case.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Archive Hidden")

    def test_database_management_export_returns_zip_bundle(self):
        self.login_as_admin()
        case = self.create_bundle_case(uhid="UH-EXPORT-001", phone_number="9000000101")
        task = Task.objects.create(case=case, title="Export review", due_date=timezone.localdate(), created_by=self.user)
        VitalEntry.objects.create(case=case, recorded_at=timezone.now(), pr=76, created_by=self.user, updated_by=self.user)
        CaseActivityLog.objects.create(case=case, task=task, user=self.user, note="Export note")
        CallLog.objects.create(case=case, task=task, outcome=CallOutcome.NO_ANSWER, notes="Export call", staff_user=self.user)

        response = self.client.post(reverse("patients:settings_database"), {"action": "export"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment;", response["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(response.content), "r") as bundle_zip:
            manifest = json.loads(bundle_zip.read(database_bundle.MANIFEST_FILENAME).decode("utf-8"))
            patient_data_bytes = bundle_zip.read(database_bundle.PATIENT_DATA_FILENAME)
            payload = json.loads(patient_data_bytes.decode("utf-8"))
        self.assertEqual(manifest["counts"]["cases"], 1)
        self.assertEqual(manifest["counts"]["tasks"], 1)
        self.assertEqual(manifest["counts"]["vitals"], 1)
        self.assertEqual(manifest["counts"]["activity_logs"], 1)
        self.assertEqual(manifest["counts"]["call_logs"], 1)
        self.assertEqual(manifest["patient_data_sha256"], hashlib.sha256(patient_data_bytes).hexdigest())
        self.assertEqual(payload["cases"][0]["uhid"], "UH-EXPORT-001")

    def test_database_management_backup_action_writes_bundle_and_shows_success(self):
        self.login_as_admin()
        self.create_bundle_case(uhid="UH-BACKUP-001", phone_number="9000000102")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            response = self.client.post(reverse("patients:settings_database"), {"action": "backup"}, follow=True)

            self.assertEqual(response.status_code, 200)
            backup_paths = sorted(Path(temp_dir).glob("patient-data-bundle-manual-*.zip"))
            self.assertEqual(len(backup_paths), 1)
            self.assertContains(response, "Saved patient-data backup to")
            self.assertContains(response, str(backup_paths[0]))
            schedule = PatientDataBackupSchedule.get_solo()
            self.assertEqual(schedule.last_backup_status, PatientDataBackupStatus.SUCCESS)
            self.assertEqual(schedule.last_backup_trigger, PatientDataBackupTrigger.MANUAL)

    def test_database_management_schedule_save_persists_and_shows_next_backup(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("patients:settings_database"),
            {
                "action": "save_schedule",
                "enabled": "on",
                "daily_time": "09:30",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        schedule = PatientDataBackupSchedule.get_solo()
        self.assertTrue(schedule.enabled)
        self.assertEqual(schedule.daily_time.strftime("%H:%M"), "09:30")
        self.assertContains(response, "Automatic backup schedules saved.")
        self.assertContains(response, "Current schedule:")
        self.assertContains(response, "Daily backups")
        self.assertContains(response, "Monthly backups")
        self.assertContains(response, "Yearly backups")

    def test_database_management_schedule_requires_daily_time_when_enabled(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("patients:settings_database"),
            {
                "action": "save_schedule",
                "enabled": "on",
                "daily_time": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backup schedule has errors.")
        self.assertContains(response, "This field is required.")

    def test_database_management_schedule_accepts_browser_time_with_seconds(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("patients:settings_database"),
            {
                "action": "save_schedule",
                "enabled": "on",
                "daily_time": "09:30:00",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        schedule = PatientDataBackupSchedule.get_solo()
        self.assertTrue(schedule.enabled)
        self.assertEqual(schedule.daily_time.strftime("%H:%M"), "09:30")
        self.assertContains(response, "Automatic backup schedules saved.")

    def test_database_management_schedule_runner_creates_daily_backup_and_updates_status(self):
        self.create_bundle_case(uhid="UH-SCHED-001", phone_number="9000000201")
        schedule = PatientDataBackupSchedule.get_solo()
        schedule.enabled = True
        schedule.daily_time = dt_time(hour=12, minute=0)
        schedule.last_monthly_backup_at = timezone.make_aware(datetime(2026, 5, 1, 0, 0))
        schedule.last_yearly_backup_at = timezone.make_aware(datetime(2026, 1, 1, 0, 0))
        schedule.save()
        reference_time = timezone.make_aware(datetime(2026, 5, 2, 13, 0))

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            ran = backup_scheduler.run_due_scheduled_backup(reference_time=reference_time)

            self.assertTrue(ran)
            self.assertEqual(len(list(Path(temp_dir).glob("patient-data-bundle-daily-*.zip"))), 1)
            schedule.refresh_from_db()
            self.assertEqual(schedule.last_backup_status, PatientDataBackupStatus.SUCCESS)
            self.assertEqual(schedule.last_backup_trigger, PatientDataBackupTrigger.DAILY_SCHEDULED)
            self.assertIsNotNone(schedule.last_backup_at)
            self.assertIsNotNone(schedule.last_daily_backup_at)
            self.assertGreater(schedule.next_backup_at(reference_time), reference_time)

            reran = backup_scheduler.run_due_scheduled_backup(reference_time=reference_time)
            self.assertFalse(reran)
            self.assertEqual(len(list(Path(temp_dir).glob("patient-data-bundle-daily-*.zip"))), 1)

    def test_database_management_schedule_runner_creates_monthly_and_yearly_archives(self):
        self.create_bundle_case(uhid="UH-SCHED-003", phone_number="9000000203")
        schedule = PatientDataBackupSchedule.get_solo()
        schedule.enabled = True
        schedule.daily_time = dt_time(hour=2, minute=0)
        schedule.last_daily_backup_at = timezone.make_aware(datetime(2026, 12, 31, 3, 0))
        schedule.save()
        reference_time = timezone.make_aware(datetime(2027, 1, 1, 0, 5))

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            ran = backup_scheduler.run_due_scheduled_backup(reference_time=reference_time)

            self.assertTrue(ran)
            self.assertEqual(len(list(Path(temp_dir).glob("patient-data-bundle-monthly-*.zip"))), 1)
            self.assertEqual(len(list(Path(temp_dir).glob("patient-data-bundle-yearly-*.zip"))), 1)
            self.assertEqual(len(list(Path(temp_dir).glob("patient-data-bundle-daily-*.zip"))), 0)
            schedule.refresh_from_db()
            self.assertIsNotNone(schedule.last_monthly_backup_at)
            self.assertIsNotNone(schedule.last_yearly_backup_at)

    def test_database_management_schedule_save_runs_due_backup_when_time_has_passed(self):
        self.login_as_admin()
        self.create_bundle_case(uhid="UH-SCHED-002", phone_number="9000000202")
        local_now = timezone.localtime()
        due_time = (local_now - timedelta(minutes=1)).time().replace(second=0, microsecond=0)
        first_of_month = timezone.make_aware(datetime(local_now.year, local_now.month, 1, 0, 0))
        start_of_year = timezone.make_aware(datetime(local_now.year, 1, 1, 0, 0))
        schedule = PatientDataBackupSchedule.get_solo()
        schedule.last_monthly_backup_at = first_of_month
        schedule.last_yearly_backup_at = start_of_year
        schedule.save()

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "save_schedule",
                    "enabled": "on",
                    "daily_time": due_time.strftime("%H:%M"),
                },
                follow=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(list(Path(temp_dir).glob("patient-data-bundle-daily-*.zip"))), 1)
            schedule = PatientDataBackupSchedule.get_solo()
            self.assertEqual(schedule.last_backup_trigger, PatientDataBackupTrigger.DAILY_SCHEDULED)
            self.assertEqual(schedule.last_backup_status, PatientDataBackupStatus.SUCCESS)

    def test_database_management_import_requires_confirmation(self):
        self.login_as_admin()
        self.create_bundle_case(uhid="UH-CONFIRM-001", phone_number="9000000103")
        bundle_bytes = self.build_patient_bundle_bytes()

        response = self.client.post(
            reverse("patients:settings_database"),
            {
                "action": "import",
                "confirm_phrase": "WRONG PHRASE",
                "bundle_file": SimpleUploadedFile("patient-data.zip", bundle_bytes, content_type="application/zip"),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, database_bundle.IMPORT_CONFIRMATION_PHRASE)
        self.assertContains(response, "Database import has errors.")

    def test_database_management_import_rejects_checksum_mismatch(self):
        self.login_as_admin()
        self.create_bundle_case(uhid="UH-CHECK-001", phone_number="9000000104")
        bad_bundle = self.rewrite_bundle(
            self.build_patient_bundle_bytes(),
            manifest_mutator=lambda manifest: manifest.__setitem__("patient_data_sha256", "0" * 64),
            refresh_manifest=False,
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "import",
                    "confirm_phrase": database_bundle.IMPORT_CONFIRMATION_PHRASE,
                    "bundle_file": SimpleUploadedFile("patient-data.zip", bad_bundle, content_type="application/zip"),
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "checksum mismatch")
        self.assertTrue(Case.objects.filter(uhid="UH-CHECK-001").exists())

    def test_database_management_import_rejects_duplicate_uhids_inside_bundle(self):
        self.login_as_admin()
        self.create_bundle_case(uhid="UH-DUP-001", phone_number="9000000105")
        duplicate_bundle = self.rewrite_bundle(
            self.build_patient_bundle_bytes(),
            payload_mutator=lambda payload: payload["cases"].append(dict(payload["cases"][0])),
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "import",
                    "confirm_phrase": database_bundle.IMPORT_CONFIRMATION_PHRASE,
                    "bundle_file": SimpleUploadedFile("patient-data.zip", duplicate_bundle, content_type="application/zip"),
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "duplicate UHIDs")

    def test_database_management_import_allows_same_name_patients_with_different_uhids(self):
        self.login_as_admin()
        self.create_bundle_case(
            uhid="UH-SAME-001",
            first_name="Lakshmi",
            last_name="Devi",
            phone_number="9000000106",
        )
        self.create_bundle_case(
            uhid="UH-SAME-002",
            first_name="Lakshmi",
            last_name="Devi",
            phone_number="9000000107",
        )
        bundle_bytes = self.build_patient_bundle_bytes()
        Case.objects.all().delete()

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "import",
                    "confirm_phrase": database_bundle.IMPORT_CONFIRMATION_PHRASE,
                    "bundle_file": SimpleUploadedFile("patient-data.zip", bundle_bytes, content_type="application/zip"),
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Case.objects.filter(first_name="Lakshmi", last_name="Devi").count(), 2)
        self.assertTrue(Case.objects.filter(uhid="UH-SAME-001").exists())
        self.assertTrue(Case.objects.filter(uhid="UH-SAME-002").exists())

    def test_database_management_import_normalizes_patient_names_and_place(self):
        self.login_as_admin()
        self.create_bundle_case(
            uhid="UH-NORM-001",
            prefix=CasePrefix.MS,
            first_name="Lakshmi",
            last_name="Devi",
            phone_number="9000000108",
        )
        bundle_bytes = self.rewrite_bundle(
            self.build_patient_bundle_bytes(),
            payload_mutator=lambda payload: payload["cases"][0].update(
                {
                    "prefix": CasePrefix.MRS,
                    "first_name": "  FIRST   NAME  ",
                    "last_name": "  lAST   NAME  ",
                    "place": "  cHENNAI  ",
                }
            ),
        )
        Case.objects.all().delete()

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "import",
                    "confirm_phrase": database_bundle.IMPORT_CONFIRMATION_PHRASE,
                    "bundle_file": SimpleUploadedFile("patient-data.zip", bundle_bytes, content_type="application/zip"),
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        case = Case.objects.get(uhid="UH-NORM-001")
        self.assertEqual(case.prefix, CasePrefix.MRS)
        self.assertEqual(case.first_name, "First Name")
        self.assertEqual(case.last_name, "Last Name")
        self.assertEqual(case.place, "Chennai")
        self.assertEqual(case.patient_name, "Mrs. First Name Last Name")

    def test_database_management_import_preserves_non_patient_settings_and_device_data(self):
        self.login_as_admin()
        theme = ThemeSettings.get_solo()
        theme.tokens = {"nav": {"bg": "#123456"}}
        theme.save()
        policy = self.enable_device_access_for(self.user)
        credential = self.create_device_credential(user=self.user, credential_id="db-settings-device")
        note = UserAdminNote.objects.create(
            user=self.user,
            temporary_password_note="Temporary nurse password",
            updated_by=self.user,
        )

        source_case = self.create_bundle_case(uhid="UH-IMPORT-001", phone_number="9000000108")
        task = Task.objects.create(case=source_case, title="Imported task", due_date=timezone.localdate(), created_by=self.user)
        VitalEntry.objects.create(case=source_case, recorded_at=timezone.now(), pr=80, created_by=self.user)
        CaseActivityLog.objects.create(case=source_case, task=task, user=self.user, note="Imported log")
        CallLog.objects.create(case=source_case, task=task, outcome=CallOutcome.CALL_BACK_LATER, staff_user=self.user)
        bundle_bytes = self.build_patient_bundle_bytes()

        Case.objects.all().delete()
        self.create_bundle_case(uhid="UH-OLD-001", phone_number="9000000109")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "import",
                    "confirm_phrase": database_bundle.IMPORT_CONFIRMATION_PHRASE,
                    "bundle_file": SimpleUploadedFile("patient-data.zip", bundle_bytes, content_type="application/zip"),
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Case.objects.filter(uhid="UH-IMPORT-001").exists())
        self.assertFalse(Case.objects.filter(uhid="UH-OLD-001").exists())
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(VitalEntry.objects.count(), 1)
        self.assertEqual(CallLog.objects.count(), 1)
        self.assertEqual(CaseActivityLog.objects.count(), 1)
        policy.refresh_from_db()
        credential.refresh_from_db()
        note.refresh_from_db()
        theme.refresh_from_db()
        self.assertTrue(policy.enabled)
        self.assertEqual(credential.credential_id, "db-settings-device")
        self.assertEqual(note.temporary_password_note, "Temporary nurse password")
        self.assertEqual(theme.tokens["nav"]["bg"], "#123456")

    def test_database_management_import_maps_missing_users_to_null(self):
        self.login_as_admin()
        imported_user = get_user_model().objects.create_user(username="imported-user", password="strong-password-123")
        source_case = self.create_bundle_case(
            uhid="UH-NULL-001",
            phone_number="9000000110",
            created_by=imported_user,
        )
        task = Task.objects.create(
            case=source_case,
            title="Missing user task",
            due_date=timezone.localdate(),
            created_by=imported_user,
            assigned_user=imported_user,
        )
        VitalEntry.objects.create(case=source_case, recorded_at=timezone.now(), pr=84, created_by=imported_user, updated_by=imported_user)
        CaseActivityLog.objects.create(case=source_case, task=task, user=imported_user, note="Missing user log")
        CallLog.objects.create(case=source_case, task=task, outcome=CallOutcome.NO_ANSWER, staff_user=imported_user)
        bundle_bytes = self.build_patient_bundle_bytes()

        Case.objects.all().delete()
        imported_user.delete()

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "import",
                    "confirm_phrase": database_bundle.IMPORT_CONFIRMATION_PHRASE,
                    "bundle_file": SimpleUploadedFile("patient-data.zip", bundle_bytes, content_type="application/zip"),
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        imported_case = Case.objects.get(uhid="UH-NULL-001")
        imported_task = Task.objects.get(case=imported_case)
        imported_vital = VitalEntry.objects.get(case=imported_case)
        imported_log = CaseActivityLog.objects.get(case=imported_case)
        imported_call = CallLog.objects.get(case=imported_case)
        self.assertIsNone(imported_case.created_by)
        self.assertIsNone(imported_task.created_by)
        self.assertIsNone(imported_task.assigned_user)
        self.assertIsNone(imported_vital.created_by)
        self.assertIsNone(imported_vital.updated_by)
        self.assertIsNone(imported_log.user)
        self.assertIsNone(imported_call.staff_user)

    def test_database_management_import_creates_missing_categories(self):
        self.login_as_admin()
        outreach = DepartmentConfig.objects.create(
            name="Outreach",
            auto_follow_up_days=14,
            predefined_actions=["Home visit"],
            metadata_template={"review_date": "Date"},
            theme_bg_color="#aabbcc",
            theme_text_color="#112233",
        )
        self.create_bundle_case(
            uhid="UH-CAT-001",
            phone_number="9000000111",
            category=outreach,
            review_date=timezone.localdate() + timedelta(days=3),
        )
        bundle_bytes = self.build_patient_bundle_bytes()

        Case.objects.all().delete()
        outreach.delete()

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "import",
                    "confirm_phrase": database_bundle.IMPORT_CONFIRMATION_PHRASE,
                    "bundle_file": SimpleUploadedFile("patient-data.zip", bundle_bytes, content_type="application/zip"),
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        recreated_category = DepartmentConfig.objects.get(name="Outreach")
        self.assertEqual(recreated_category.theme_bg_color, "#aabbcc")
        self.assertEqual(recreated_category.theme_text_color, "#112233")
        self.assertTrue(Case.objects.filter(category=recreated_category, uhid="UH-CAT-001").exists())

    def test_database_management_import_rolls_back_on_internal_error(self):
        self.login_as_admin()
        self.create_bundle_case(uhid="UH-ROLLBACK-SOURCE", phone_number="9000000112")
        bundle_bytes = self.build_patient_bundle_bytes()
        Case.objects.all().delete()
        self.create_bundle_case(uhid="UH-ROLLBACK-TARGET", phone_number="9000000113")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "patients.database_bundle.default_backup_dir", return_value=Path(temp_dir)
        ), patch("patients.database_bundle._import_payload", side_effect=RuntimeError("boom")):
            response = self.client.post(
                reverse("patients:settings_database"),
                {
                    "action": "import",
                    "confirm_phrase": database_bundle.IMPORT_CONFIRMATION_PHRASE,
                    "bundle_file": SimpleUploadedFile("patient-data.zip", bundle_bytes, content_type="application/zip"),
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Database import failed: boom")
        self.assertTrue(Case.objects.filter(uhid="UH-ROLLBACK-TARGET").exists())

    def test_device_access_page_can_save_selected_target_users(self):
        pilot_user = get_user_model().objects.create_user(username="pilot-user", password="strong-password-123")

        self.login_as_admin()
        response = self.client.post(
            reverse("patients:settings_device_access"),
            {
                "action": "save_policy",
                "enabled": "on",
                "target_users": [str(pilot_user.pk)],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        policy = DeviceApprovalPolicy.get_solo()
        self.assertTrue(policy.enabled)
        self.assertEqual(list(policy.target_users.order_by("pk")), [pilot_user])
        self.assertContains(response, "Device approval pilot settings saved.")

    def test_device_access_page_clones_staff_pilot_role_from_staff(self):
        RoleSetting.objects.update_or_create(
            role_name=STAFF_ROLE_NAME,
            defaults={
                "can_case_create": True,
                "can_case_edit": True,
                "can_task_create": True,
                "can_task_edit": False,
                "can_note_add": True,
                "can_manage_settings": False,
            },
        )

        self.login_as_admin()
        response = self.client.post(reverse("patients:settings_device_access"), {"action": "clone_staff_pilot"})

        self.assertEqual(response.status_code, 302)
        staff_role = RoleSetting.objects.get(role_name=STAFF_ROLE_NAME)
        pilot_role = RoleSetting.objects.get(role_name=STAFF_PILOT_ROLE_NAME)
        self.assertEqual(pilot_role.field_capabilities(), staff_role.field_capabilities())
        self.assertTrue(Group.objects.filter(name=STAFF_PILOT_ROLE_NAME).exists())

    def test_non_targeted_user_login_still_works_normally(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "strong-password-123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("patients:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_targeted_user_login_redirects_to_device_verification(self):
        pilot_user = get_user_model().objects.create_user(username="pilot-login", password="strong-password-123")
        Group.objects.get_or_create(name=STAFF_PILOT_ROLE_NAME)[0]
        self.enable_device_access_for(pilot_user)

        response = self.client.post(
            reverse("login"),
            {"username": pilot_user.username, "password": "strong-password-123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login_device_verification"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_device_registration_creates_pending_credential_without_login(self):
        pilot_user = get_user_model().objects.create_user(username="pilot-register", password="strong-password-123")
        self.enable_device_access_for(pilot_user)
        self.client.post(reverse("login"), {"username": pilot_user.username, "password": "strong-password-123"})

        deps = self.fake_registration_webauthn_deps(credential_id=b"pending-registration-device")
        with patch("patients.views._load_webauthn_dependencies", return_value=deps):
            options_response = self.client.post(reverse("login_device_register_options"))
            verify_response = self.client.post(
                reverse("login_device_register_verify"),
                data=json.dumps(
                    {
                        "device_label": "Pilot ward PC",
                        "credential": {"id": "pending-registration-device", "type": "public-key"},
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(options_response.status_code, 200)
        self.assertEqual(verify_response.status_code, 200)
        credential = StaffDeviceCredential.objects.get(user=pilot_user)
        self.assertEqual(credential.status, StaffDeviceCredentialStatus.PENDING)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_targeted_user_with_trusted_device_cookie_can_log_in(self):
        pilot_user = get_user_model().objects.create_user(username="pilot-cookie", password="strong-password-123")
        self.enable_device_access_for(pilot_user)
        credential = self.create_device_credential(
            user=pilot_user,
            credential_id="approved-cookie-device",
            trusted_token="trusted-cookie-token",
        )
        self.client.cookies[settings.DEVICE_APPROVAL_TRUST_COOKIE_NAME] = f"{credential.pk}:trusted-cookie-token"

        response = self.client.post(
            reverse("login"),
            {"username": pilot_user.username, "password": "strong-password-123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("patients:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), pilot_user.pk)

    def test_targeted_user_without_trusted_cookie_is_redirected_even_if_device_is_approved(self):
        pilot_user = get_user_model().objects.create_user(username="pilot-no-cookie", password="strong-password-123")
        self.enable_device_access_for(pilot_user)
        self.create_device_credential(user=pilot_user, credential_id="approved-no-cookie")

        response = self.client.post(
            reverse("login"),
            {"username": pilot_user.username, "password": "strong-password-123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login_device_verification"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_revoked_device_cookie_no_longer_bypasses_targeted_login(self):
        pilot_user = get_user_model().objects.create_user(username="pilot-revoked", password="strong-password-123")
        self.enable_device_access_for(pilot_user)
        revoked = self.create_device_credential(
            user=pilot_user,
            status=StaffDeviceCredentialStatus.REVOKED,
            credential_id="revoked-device",
            trusted_token="revoked-token",
        )
        self.client.cookies[settings.DEVICE_APPROVAL_TRUST_COOKIE_NAME] = f"{revoked.pk}:revoked-token"

        response = self.client.post(
            reverse("login"),
            {"username": pilot_user.username, "password": "strong-password-123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login_device_verification"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_device_authentication_verification_logs_in_targeted_user_and_sets_cookie(self):
        pilot_user = get_user_model().objects.create_user(username="pilot-verify", password="strong-password-123")
        self.enable_device_access_for(pilot_user)
        credential = self.create_device_credential(user=pilot_user, credential_id="approved-credential")
        self.client.post(reverse("login"), {"username": pilot_user.username, "password": "strong-password-123"})

        deps = self.fake_authentication_webauthn_deps(new_sign_count=9)
        with patch("patients.views._load_webauthn_dependencies", return_value=deps):
            options_response = self.client.post(reverse("login_device_authenticate_options"))
            verify_response = self.client.post(
                reverse("login_device_authenticate_verify"),
                data=json.dumps({"credential": {"id": credential.credential_id, "type": "public-key"}}),
                content_type="application/json",
            )

        self.assertEqual(options_response.status_code, 200)
        self.assertEqual(verify_response.status_code, 200)
        credential.refresh_from_db()
        self.assertEqual(int(self.client.session["_auth_user_id"]), pilot_user.pk)
        self.assertTrue(credential.trusted_token_hash)
        self.assertEqual(credential.sign_count, 9)
        self.assertIn(settings.DEVICE_APPROVAL_TRUST_COOKIE_NAME, verify_response.cookies)

    def test_device_registration_is_blocked_after_three_approved_devices(self):
        pilot_user = get_user_model().objects.create_user(username="pilot-cap", password="strong-password-123")
        self.enable_device_access_for(pilot_user)
        for index in range(DEVICE_APPROVAL_MAX_APPROVED):
            self.create_device_credential(user=pilot_user, credential_id=f"approved-cap-{index}")

        self.client.post(reverse("login"), {"username": pilot_user.username, "password": "strong-password-123"})
        response = self.client.post(reverse("login_device_register_options"))

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "already has", status_code=400)

    def test_admin_cannot_approve_fourth_device_for_user(self):
        pilot_user = get_user_model().objects.create_user(username="pilot-approve-cap", password="strong-password-123")
        for index in range(DEVICE_APPROVAL_MAX_APPROVED):
            self.create_device_credential(user=pilot_user, credential_id=f"approved-limit-{index}")
        pending = self.create_device_credential(
            user=pilot_user,
            status=StaffDeviceCredentialStatus.PENDING,
            credential_id="pending-limit",
            device_label="Overflow browser",
        )

        self.login_as_admin()
        response = self.client.post(
            reverse("patients:settings_device_access"),
            {"action": "approve_device", "credential_id": pending.pk},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.status, StaffDeviceCredentialStatus.PENDING)
        self.assertContains(response, "already has 3 approved devices")

    def test_theme_settings_page_saves_global_tokens_and_category_colors(self):
        self.login_as_admin()
        anc = DepartmentConfig.objects.get(name="ANC")
        post_data = self.build_theme_post_data(
            token_overrides={
                "nav__bg": "#123456",
                "case_header__bg": "#654321",
                "shell__page_bg": "#faf0e6",
                "dashboard__recent__bg": "#c7ddff",
                "dashboard__recent__text": "#163ea8",
                "search__gender_male__bg": "#ccddee",
                "search__gender_other__text": "#334455",
            },
            category_overrides={"ANC": {"bg": "#abcdef", "text": "#123456"}},
        )

        response = self.client.post(reverse("patients:settings_theme"), post_data, follow=True)

        self.assertEqual(response.status_code, 200)
        theme_settings = ThemeSettings.get_solo()
        anc.refresh_from_db()
        self.assertEqual(theme_settings.tokens["nav"]["bg"], "#123456")
        self.assertEqual(theme_settings.tokens["case_header"]["bg"], "#654321")
        self.assertEqual(theme_settings.tokens["shell"]["page_bg"], "#faf0e6")
        self.assertEqual(theme_settings.tokens["dashboard"]["recent"]["bg"], "#c7ddff")
        self.assertEqual(theme_settings.tokens["dashboard"]["recent"]["text"], "#163ea8")
        self.assertEqual(theme_settings.tokens["search"]["gender_male"]["bg"], "#ccddee")
        self.assertEqual(theme_settings.tokens["search"]["gender_other"]["text"], "#334455")
        self.assertEqual(anc.theme_bg_color, "#abcdef")
        self.assertEqual(anc.theme_text_color, "#123456")
        self.assertContains(response, "--theme-nav-bg: #123456;")
        self.assertContains(response, "--theme-case-header-bg: #654321;")
        self.assertContains(response, "--theme-dashboard-recent-bg: #c7ddff;")
        self.assertContains(response, "--theme-search-gender-male-bg: #ccddee;")
        self.assertContains(response, "--theme-search-gender-other-text: #334455;")
        self.assertContains(response, "Theme settings saved.")

    def test_theme_settings_restore_defaults_resets_saved_values(self):
        self.login_as_admin()
        anc = DepartmentConfig.objects.get(name="ANC")
        surgery = DepartmentConfig.objects.get(name="Surgery")
        medicine = DepartmentConfig.objects.get(name="Medicine")
        theme_settings = ThemeSettings.get_solo()
        theme_settings.tokens = {"nav": {"bg": "#123456"}}
        theme_settings.save()
        anc.theme_bg_color = "#abcdef"
        anc.theme_text_color = "#123456"
        anc.save()
        surgery.theme_bg_color = "#112233"
        surgery.theme_text_color = "#445566"
        surgery.save()
        medicine.theme_bg_color = "#778899"
        medicine.theme_text_color = "#aabbcc"
        medicine.save()

        response = self.client.post(
            reverse("patients:settings_theme"),
            {"action": "restore_defaults"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        theme_settings.refresh_from_db()
        anc.refresh_from_db()
        surgery.refresh_from_db()
        medicine.refresh_from_db()
        self.assertEqual(theme_settings.tokens["nav"]["bg"], "#fffdf8")
        self.assertEqual(theme_settings.tokens["dashboard"]["recent"]["bg"], "#d1c4e9")
        self.assertEqual(anc.theme_bg_color, "#ffe0b2")
        self.assertEqual(anc.theme_text_color, "#bf360c")
        self.assertEqual(surgery.theme_bg_color, "#b2dfdb")
        self.assertEqual(surgery.theme_text_color, "#004d40")
        self.assertEqual(medicine.theme_bg_color, "#c5cae9")
        self.assertEqual(medicine.theme_text_color, "#1a237e")
        self.assertContains(response, "Theme restored to defaults.")

    def test_error_messages_render_as_danger_alerts(self):
        self.login_as_admin()

        response = self.client.post(
            reverse("patients:settings_user_management"),
            {"action": "create_role", "tab": "roles"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert alert-danger mb-2")

    def test_admin_changelog_page_displays_version_entries(self):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:changelog"))

        self.assertEqual(response.status_code, 200)
        app_version = Path("VERSION").read_text(encoding="utf-8").strip()
        self.assertContains(response, f"Version {app_version}")
        self.assertContains(response, "Added a changelog page")


    def test_seed_mock_data_settings_page_access_and_links(self):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("patients:settings_seed_mock_data"))

        seed_page = self.client.get(reverse("patients:settings_seed_mock_data"))
        self.assertEqual(seed_page.status_code, 200)
        self.assertContains(seed_page, "Seed Mock Data")
        self.assertContains(seed_page, "Delete all mock data")

    @patch("patients.views.call_command")
    def test_seed_mock_data_settings_page_runs_seed_command(self, call_command_mock):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:settings_seed_mock_data"),
            {
                "action": "reseed",
                "profile": "smoke",
                "count": "8",
                "include_vitals": "on",
                "include_rch_scenarios": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        call_command_mock.assert_called_once_with(
            "seed_mock_data",
            "--count",
            "8",
            "--profile",
            "smoke",
            "--include-vitals",
            "--include-rch-scenarios",
            "--reset",
        )

    @patch("patients.views.call_command")
    def test_seed_mock_data_settings_reset_all_requires_confirmation(self, call_command_mock):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:settings_seed_mock_data"),
            {
                "action": "seed",
                "profile": "smoke",
                "reset_all": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        call_command_mock.assert_not_called()
        self.assertContains(response, "Please confirm reset-all before continuing.")

    @patch("patients.views.call_command")
    def test_seed_mock_data_settings_reset_all_passes_yes_flag_when_confirmed(self, call_command_mock):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:settings_seed_mock_data"),
            {
                "action": "seed",
                "profile": "smoke",
                "reset_all": "on",
                "confirm_reset_all": "true",
            },
        )

        self.assertEqual(response.status_code, 302)
        call_command_mock.assert_called_once_with(
            "seed_mock_data",
            "--profile",
            "smoke",
            "--reset-all",
            "--yes-reset-all",
        )

    def test_seed_mock_data_settings_delete_seeded_only(self):
        ensure_default_departments()
        surgery = DepartmentConfig.objects.get(name="Surgery")

        seeded_case = Case.objects.create(
            uhid="UH-SEED-DEL-1",
            first_name="Seeded",
            last_name="Case",
            phone_number="9888888800",
            category=surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
            metadata={"source": "seed_mock_data"},
        )
        Case.objects.create(
            uhid="UH-SEED-DEL-2",
            first_name="Manual",
            last_name="Case",
            phone_number="9888888801",
            category=surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
            metadata={"source": "manual_entry"},
        )
        CallLog.objects.create(case=seeded_case, outcome=CallOutcome.NO_ANSWER, notes="seeded", staff_user=self.user)

        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

        response = self.client.post(reverse("patients:settings_seed_mock_data"), {"action": "delete_seeded"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Case.objects.filter(metadata__source="seed_mock_data").exists())
        self.assertTrue(Case.objects.filter(metadata__source="manual_entry").exists())

    def test_create_case_saves_gender_dob_and_place(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH444",
                "prefix": CasePrefix.MS,
                "first_name": "Asha",
                "last_name": "Devi",
                "gender": "FEMALE",
                "date_of_birth": "1995-01-15",
                "place": "Chennai",
                "phone_number": "9123456789",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": (timezone.localdate() + timedelta(days=14)).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(uhid="UH444")
        self.assertEqual(case.gender, "FEMALE")
        self.assertEqual(case.place, "Chennai")
        self.assertEqual(case.date_of_birth.isoformat(), "1995-01-15")

    def test_create_case_normalizes_patient_names_and_place(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH444N",
                "prefix": CasePrefix.MRS,
                "first_name": "  FIRST   NAME  ",
                "last_name": "  lAST   NAME  ",
                "gender": "FEMALE",
                "date_of_birth": "1995-01-15",
                "place": "  cHENNAI  ",
                "phone_number": "9123456790",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": (timezone.localdate() + timedelta(days=14)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(uhid="UH444N")
        self.assertEqual(case.prefix, CasePrefix.MRS)
        self.assertEqual(case.first_name, "First Name")
        self.assertEqual(case.last_name, "Last Name")
        self.assertEqual(case.place, "Chennai")
        self.assertEqual(case.patient_name, "Mrs. First Name Last Name")

    def test_case_form_accepts_india_style_date_input(self):
        review_date = timezone.localdate() + timedelta(days=10)
        form = CaseForm(
            data={
                "uhid": "UH444A",
                "prefix": CasePrefix.MS,
                "first_name": "Asha",
                "last_name": "Devi",
                "gender": "FEMALE",
                "date_of_birth": "15/01/1995",
                "place": "Chennai",
                "phone_number": "9123456788",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": review_date.strftime("%d/%m/%Y"),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["date_of_birth"].isoformat(), "1995-01-15")
        self.assertEqual(form.cleaned_data["review_date"], review_date)

    def test_case_form_uses_dob_to_calculate_age(self):
        dob = timezone.localdate() - timedelta(days=365 * 25)
        form = CaseForm(
            data={
                "uhid": "UH-AGE1",
                "prefix": CasePrefix.MR,
                "first_name": "Age",
                "last_name": "Auto",
                "phone_number": "9876500077",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "date_of_birth": dob.isoformat(),
                "age": "",
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": (timezone.localdate() + timedelta(days=10)).isoformat(),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        today = timezone.localdate()
        expected_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        self.assertEqual(form.cleaned_data["age"], expected_age)

    def test_case_form_marks_date_fields_for_crayons_datepicker(self):
        form = CaseForm()

        for field_name in ["date_of_birth", "lmp", "edd", "usg_edd", "surgery_date", "review_date"]:
            self.assertEqual(form.fields[field_name].widget.attrs["data-crayons-datepicker"], "true")
            self.assertEqual(form.fields[field_name].widget.attrs["data-crayons-datepicker-format"], "dd/MM/yyyy")
            self.assertEqual(form.fields[field_name].widget.attrs["data-crayons-datepicker-locale"], "en-IN")
            self.assertEqual(form.fields[field_name].widget.attrs["data-crayons-datepicker-show-footer"], "false")

    def test_case_create_preview_requires_authentication(self):
        response = self.client.post(reverse("patients:case_create_preview"), {"category": self.anc.id})

        self.assertEqual(response.status_code, 302)

    def test_case_create_preview_requires_case_create_capability(self):
        self.login_as_role("Nurse", username="nurse_preview")

        response = self.client.post(reverse("patients:case_create_preview"), {"category": self.anc.id})

        self.assertEqual(response.status_code, 403)

    def test_case_create_preview_returns_anc_oob_fragment_without_writing_records(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create_preview"),
            {
                "category": self.anc.id,
                "lmp": (timezone.localdate() - timedelta(days=56)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=210)).isoformat(),
                "rch_bypass": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-swap-oob="outerHTML"')
        self.assertContains(response, "Routine prenatal check up")
        self.assertContains(response, "RCH bypass is active")
        self.assertFalse(Case.objects.filter(uhid="UH-PREVIEW").exists())
        self.assertFalse(Task.objects.exists())

    def test_case_create_preview_moves_surgery_subcategory_into_step_one_oob_fragment(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create_preview"),
            {
                "category": self.surgery.id,
            },
            HTTP_HX_REQUEST="true",
        )
        response_text = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="case-create-subcategory-shell"')
        self.assertContains(response, 'id="case-create-subcategory-shell"', count=1)
        self.assertContains(response, 'name="subcategory"', count=1)
        self.assertContains(response, "Choose the surgical specialty.")
        self.assertIn('id="case-create-subcategory-shell"', response_text)
        self.assertLess(
            response_text.index('id="case-create-subcategory-shell"'),
            response_text.index('id="case-create-workflow-panel"'),
        )

    def test_case_create_preview_supports_generic_category_without_review_date(self):
        custom_category = DepartmentConfig.objects.create(
            name="Custom Clinic",
            predefined_actions=["Custom Review"],
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create_preview"),
            {
                "category": custom_category.id,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Capture the next clinical action clearly.")
        self.assertContains(response, "Custom Review")
        self.assertNotContains(response, "Add review date to unlock the starter-task preview.")

    def test_case_create_preview_renders_gpla_stepper_controls_for_anc(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create_preview"),
            {
                "category": self.anc.id,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-gpla-counter")
        self.assertContains(response, "data-gpla-primi-toggle")
        self.assertContains(response, "Primi")
        self.assertContains(response, 'id="case-create-gpla-summary"')
        self.assertContains(response, "G0 P0 A0 L0")
        self.assertNotContains(response, '<select name="gravida"')

    def test_case_create_identity_check_requires_case_create_capability(self):
        self.login_as_role("Nurse", username="nurse_identity")

        response = self.client.post(reverse("patients:case_create_identity_check"), {"uhid": "UH001"})

        self.assertEqual(response.status_code, 403)

    def test_case_create_identity_check_warns_on_active_uhid_and_phone_matches(self):
        existing_case = Case.objects.create(
            uhid="UH-ID-CHECK",
            first_name="Existing",
            last_name="Record",
            phone_number="9876500550",
            alternate_phone_number="9876500551",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("patients:case_create_identity_check"),
            {
                "uhid": "UH-ID-CHECK",
                "phone_number": "9876500550",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Existing case uses this UHID")
        self.assertContains(response, "Phone number matches an existing case")
        self.assertContains(response, reverse("patients:case_detail", kwargs={"pk": existing_case.pk}))

    def test_case_create_identity_check_shows_both_phone_warnings_when_one_number_has_many_matches(self):
        self.client.force_login(self.user)
        base_time = timezone.now()
        for index in range(8):
            crowded_case = Case.objects.create(
                uhid=f"UH-ID-CROWD-{index}",
                first_name="Crowded",
                last_name="Phone",
                phone_number="9876500660",
                category=self.surgery,
                status=CaseStatus.ACTIVE,
                surgical_pathway=SurgicalPathway.SURVEILLANCE,
                review_date=timezone.localdate() + timedelta(days=5),
                created_by=self.user,
            )
            Case.objects.filter(pk=crowded_case.pk).update(updated_at=base_time + timedelta(minutes=index))

        alternate_match = Case.objects.create(
            uhid="UH-ID-ALT",
            first_name="Alternate",
            last_name="Phone",
            phone_number="9876500770",
            alternate_phone_number="9876500771",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )
        Case.objects.filter(pk=alternate_match.pk).update(updated_at=base_time - timedelta(days=2))

        response = self.client.post(
            reverse("patients:case_create_identity_check"),
            {
                "phone_number": "9876500660",
                "alternate_phone_number": "9876500771",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Phone number matches an existing case")
        self.assertContains(response, "Alternate phone number matches an existing case")
        self.assertContains(response, reverse("patients:case_detail", kwargs={"pk": alternate_match.pk}))

    def test_dashboard_recent_panel_uses_inline_detail_container_without_modal_markup(self):
        self.client.force_login(self.user)
        self.create_recent_case()
        response = self.client.get(reverse("patients:dashboard"))

        self.assertContains(response, "data-recent-case-detail")
        self.assertNotContains(response, "recentCaseModal")

    def test_case_form_requires_age_when_dob_missing(self):
        form = CaseForm(
            data={
                "uhid": "UH-AGE2",
                "prefix": CasePrefix.MR,
                "first_name": "Age",
                "last_name": "Manual",
                "phone_number": "9876500078",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": (timezone.localdate() + timedelta(days=10)).isoformat(),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("age", form.errors)

    def test_case_form_requires_anc_high_risk_reasons_when_high_risk_checked(self):
        form = CaseForm(
            data={
                "uhid": "UH-HR-ANC-1",
                "prefix": CasePrefix.MRS,
                "first_name": "High",
                "last_name": "Risk",
                "phone_number": "9876500091",
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "21",
                "lmp": (timezone.localdate() - timedelta(days=56)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=210)).isoformat(),
                "rch_number": "987654321",
                "high_risk": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("anc_high_risk_reasons", form.errors)

    def test_case_form_accepts_anc_high_risk_reasons(self):
        form = CaseForm(
            data={
                "uhid": "UH-HR-ANC-2",
                "prefix": CasePrefix.MRS,
                "first_name": "Reasoned",
                "last_name": "Risk",
                "phone_number": "9876500092",
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "24",
                "lmp": (timezone.localdate() - timedelta(days=56)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=210)).isoformat(),
                "rch_number": "123456789",
                "high_risk": "on",
                "anc_high_risk_reasons": [AncHighRiskReason.ANEMIA, AncHighRiskReason.PIH],
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["anc_high_risk_reasons"], [AncHighRiskReason.ANEMIA, AncHighRiskReason.PIH])

    def test_case_form_requires_rch_number_or_bypass_for_anc(self):
        form = CaseForm(
            data={
                "uhid": "UH-RCH-ANC-1",
                "prefix": CasePrefix.MS,
                "first_name": "Rch",
                "last_name": "Required",
                "phone_number": "9876500191",
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "25",
                "lmp": (timezone.localdate() - timedelta(days=56)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=210)).isoformat(),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("rch_number", form.errors)

    def test_case_form_accepts_rch_bypass_without_rch_number(self):
        form = CaseForm(
            data={
                "uhid": "UH-RCH-ANC-2",
                "prefix": CasePrefix.MS,
                "first_name": "Rch",
                "last_name": "Bypass",
                "phone_number": "9876500192",
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "25",
                "lmp": (timezone.localdate() - timedelta(days=56)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=210)).isoformat(),
                "rch_bypass": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["rch_bypass"])
        self.assertEqual(form.cleaned_data["rch_number"], "")

    def test_case_form_rejects_non_digit_rch_number(self):
        form = CaseForm(
            data={
                "uhid": "UH-RCH-ANC-3",
                "prefix": CasePrefix.MS,
                "first_name": "Rch",
                "last_name": "Invalid",
                "phone_number": "9876500193",
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "25",
                "lmp": (timezone.localdate() - timedelta(days=56)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=210)).isoformat(),
                "rch_number": "RCH12A",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("rch_number", form.errors)

    def test_case_form_forces_bypass_false_when_rch_number_present(self):
        form = CaseForm(
            data={
                "uhid": "UH-RCH-ANC-4",
                "prefix": CasePrefix.MS,
                "first_name": "Rch",
                "last_name": "Reset",
                "phone_number": "9876500194",
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "25",
                "lmp": (timezone.localdate() - timedelta(days=56)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=210)).isoformat(),
                "rch_number": "123456789",
                "rch_bypass": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["rch_bypass"])

    def test_anc_case_create_with_rch_bypass_schedules_reminder_task(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH-RCH-CREATE",
                "prefix": CasePrefix.MR,
                "first_name": "Reminder",
                "last_name": "Create",
                "phone_number": "9876500195",
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "26",
                "lmp": (timezone.localdate() - timedelta(days=56)).isoformat(),
                "edd": (timezone.localdate() + timedelta(days=210)).isoformat(),
                "rch_bypass": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(uhid="UH-RCH-CREATE")
        reminder = case.tasks.filter(title=RCH_REMINDER_TASK_TITLE, status=TaskStatus.SCHEDULED).first()
        self.assertIsNotNone(reminder)
        self.assertEqual(reminder.due_date, timezone.localdate() + timedelta(days=RCH_REMINDER_INTERVAL_DAYS))

    def test_anc_case_update_with_rch_number_cancels_open_rch_reminders(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-RCH-UPDATE",
            prefix=CasePrefix.MR,
            first_name="Reminder",
            last_name="Cancel",
            phone_number="9876500196",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=timezone.localdate() - timedelta(days=56),
            edd=timezone.localdate() + timedelta(days=210),
            rch_bypass=True,
            created_by=self.user,
        )
        reminder = Task.objects.create(
            case=case,
            title=RCH_REMINDER_TASK_TITLE,
            due_date=timezone.localdate() + timedelta(days=3),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_edit", kwargs={"pk": case.pk}),
            {
                "uhid": case.uhid,
                "prefix": case.prefix,
                "first_name": case.first_name,
                "last_name": case.last_name,
                "phone_number": case.phone_number,
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "26",
                "lmp": case.lmp.isoformat(),
                "edd": case.edd.isoformat(),
                "rch_number": "9988776655",
            },
        )

        self.assertEqual(response.status_code, 302)
        reminder.refresh_from_db()
        case.refresh_from_db()
        self.assertEqual(reminder.status, TaskStatus.CANCELLED)
        self.assertFalse(case.rch_bypass)

    def test_case_update_normalizes_patient_names(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-EDIT-NAME",
            prefix=CasePrefix.MS,
            first_name="Asha",
            last_name="Devi",
            place="Pune",
            phone_number="9876500198",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            review_date=timezone.localdate() + timedelta(days=7),
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_edit", kwargs={"pk": case.pk}),
            {
                "uhid": case.uhid,
                "prefix": CasePrefix.MRS,
                "first_name": "  FIRST   NAME ",
                "last_name": "  lAST   NAME ",
                "place": "  nEW   dELHI  ",
                "phone_number": case.phone_number,
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "age": "26",
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": case.review_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.prefix, CasePrefix.MRS)
        self.assertEqual(case.first_name, "First Name")
        self.assertEqual(case.last_name, "Last Name")
        self.assertEqual(case.place, "New Delhi")
        self.assertEqual(case.patient_name, "Mrs. First Name Last Name")

    def test_case_update_requires_prefix_for_legacy_blank_prefix_case(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-EDIT-LEGACY-PREFIX",
            first_name="Legacy",
            last_name="Case",
            phone_number="9876500891",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_edit", kwargs={"pk": case.pk}),
            {
                "uhid": case.uhid,
                "prefix": "",
                "first_name": case.first_name,
                "last_name": case.last_name,
                "phone_number": case.phone_number,
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "age": "31",
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": case.review_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertContains(response, 'name="prefix"')

    def test_case_edit_page_uses_new_case_shell_with_status_and_summary_rail(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-EDIT-SHELL",
            first_name="Asha",
            last_name="Devi",
            place="Pune",
            phone_number="9876500880",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_edit", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="case-edit-form"')
        self.assertContains(response, 'id="case-edit-preview-sync"')
        self.assertContains(response, 'id="case-edit-identity-sync"')
        self.assertContains(response, 'id="case-edit-summary-panel"')
        self.assertContains(response, "Edit Summary")
        self.assertContains(response, "data-case-edit-submit-button")
        self.assertContains(response, "case-create-choice-grid")
        self.assertContains(response, 'type="radio" name="category"')
        self.assertContains(response, 'name="prefix"')
        self.assertContains(response, 'name="status"')

    def test_case_edit_preview_requires_case_edit_capability(self):
        self.login_as_role("Nurse", username="nurse_edit_preview")
        case = Case.objects.create(
            uhid="UH-EDIT-PREVIEW-AUTH",
            first_name="Protected",
            last_name="Case",
            phone_number="9876500881",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            created_by=self.user,
        )

        response = self.client.post(reverse("patients:case_edit_preview", kwargs={"pk": case.pk}), {"category": self.anc.id})

        self.assertEqual(response.status_code, 403)

    def test_case_edit_preview_returns_oob_fragment_without_starter_task_language(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-EDIT-PREVIEW",
            first_name="Edited",
            last_name="ANC",
            phone_number="9876500882",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=timezone.localdate() - timedelta(days=56),
            edd=timezone.localdate() + timedelta(days=210),
            rch_bypass=True,
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Routine prenatal check up",
            due_date=timezone.localdate() + timedelta(days=2),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_edit_preview", kwargs={"pk": case.pk}),
            {
                "uhid": case.uhid,
                "first_name": case.first_name,
                "last_name": case.last_name,
                "phone_number": case.phone_number,
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "26",
                "lmp": case.lmp.isoformat(),
                "edd": case.edd.isoformat(),
                "rch_bypass": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-swap-oob="outerHTML"')
        self.assertContains(response, "Edit Summary")
        self.assertContains(response, "Open tasks")
        self.assertContains(response, "Editing a case does not recreate starter tasks.")
        self.assertNotContains(response, "Starter tasks")

    def test_case_edit_preview_summary_shows_empty_state_when_nothing_changed(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-EDIT-NO-CHANGES",
            first_name="Calm",
            last_name="Draft",
            phone_number="9876500894",
            category=self.surgery,
            subcategory=CaseSubcategory.GENERAL_SURGERY,
            status=CaseStatus.ACTIVE,
            age=32,
            place="Nagpur",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_edit_preview", kwargs={"pk": case.pk}),
            {
                "uhid": case.uhid,
                "first_name": case.first_name,
                "last_name": case.last_name,
                "phone_number": case.phone_number,
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": case.status,
                "age": str(case.age),
                "place": case.place,
                "surgical_pathway": case.surgical_pathway,
                "review_date": case.review_date.isoformat(),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No unsaved changes yet.")

    def test_case_edit_preview_summary_lists_subcategory_change(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-EDIT-SUBCATEGORY",
            first_name="Edited",
            last_name="Subcategory",
            phone_number="9876500893",
            category=self.surgery,
            subcategory=CaseSubcategory.GENERAL_SURGERY,
            status=CaseStatus.ACTIVE,
            age=30,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_edit_preview", kwargs={"pk": case.pk}),
            {
                "uhid": case.uhid,
                "first_name": case.first_name,
                "last_name": case.last_name,
                "phone_number": case.phone_number,
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.ORTHOPEDICS,
                "status": case.status,
                "age": str(case.age),
                "surgical_pathway": case.surgical_pathway,
                "review_date": case.review_date.isoformat(),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Subcategory")
        self.assertContains(response, "General Surgery")
        self.assertContains(response, "Orthopedics")

    def test_case_edit_preview_summary_lists_changed_fields_and_risk_details(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-EDIT-DIFFS",
            first_name="Draft",
            last_name="Review",
            phone_number="9876500884",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            age=27,
            high_risk=True,
            lmp=timezone.localdate() - timedelta(days=56),
            edd=timezone.localdate() + timedelta(days=210),
            gravida=2,
            para=1,
            abortions=0,
            living=1,
            ncd_flags=[NonCommunicableDisease.T2DM],
            anc_high_risk_reasons=[AncHighRiskReason.ANEMIA],
            notes="Initial summary note",
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_edit_preview", kwargs={"pk": case.pk}),
            {
                "uhid": case.uhid,
                "first_name": case.first_name,
                "last_name": case.last_name,
                "phone_number": case.phone_number,
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "28",
                "high_risk": "on",
                "lmp": case.lmp.isoformat(),
                "edd": case.edd.isoformat(),
                "gravida": "4",
                "para": "2",
                "abortions": "1",
                "living": "2",
                "ncd_flags": [NonCommunicableDisease.T2DM, NonCommunicableDisease.SHTN],
                "anc_high_risk_reasons": [AncHighRiskReason.PREVIOUS_LSCS],
                "notes": "Updated note for summary panel",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Changed Fields")
        self.assertContains(response, 'class="case-edit-change-after"')
        self.assertContains(response, "GPAL")
        self.assertContains(response, "G2 P1 A0 L1")
        self.assertContains(response, "G4 P2 A1 L2")
        self.assertContains(response, "NCD flags")
        self.assertContains(response, "Added")
        self.assertContains(response, "SHTN")
        self.assertContains(response, "Removed")
        self.assertContains(response, "Anemia")
        self.assertContains(response, "Previous LSCS")
        self.assertContains(response, "Updated note for summary panel")

    def test_case_edit_identity_check_excludes_current_case_and_shows_other_matches(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-EDIT-IDENTITY",
            first_name="Primary",
            last_name="Record",
            phone_number="9876500883",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=self.user,
        )
        other_case = Case.objects.create(
            uhid="UH-EDIT-IDENTITY-OTHER",
            first_name="Sibling",
            last_name="Record",
            phone_number="9876500883",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=9),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_edit_identity_check", kwargs={"pk": case.pk}),
            {
                "uhid": case.uhid,
                "phone_number": case.phone_number,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Existing case uses this UHID")
        self.assertContains(response, "Phone number matches an existing case")
        self.assertContains(response, reverse("patients:case_detail", kwargs={"pk": other_case.pk}))
        self.assertNotContains(response, reverse("patients:case_detail", kwargs={"pk": case.pk}))

    def test_completing_rch_reminder_schedules_next_reminder_when_rch_missing(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-RCH-CHAIN",
            first_name="Reminder",
            last_name="Chain",
            phone_number="9876500197",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=timezone.localdate() - timedelta(days=56),
            edd=timezone.localdate() + timedelta(days=210),
            rch_bypass=True,
            created_by=self.user,
        )
        task = Task.objects.create(
            case=case,
            title=RCH_REMINDER_TASK_TITLE,
            due_date=timezone.localdate(),
            status=TaskStatus.SCHEDULED,
            task_type="CALL",
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:task_edit", kwargs={"pk": task.pk}),
            {
                "title": task.title,
                "due_date": task.due_date.isoformat(),
                "status": TaskStatus.COMPLETED,
                "assigned_user": "",
                "task_type": task.task_type,
                "frequency_label": task.frequency_label,
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        next_reminder = (
            case.tasks.exclude(pk=task.pk)
            .filter(title=RCH_REMINDER_TASK_TITLE, status=TaskStatus.SCHEDULED)
            .first()
        )
        self.assertIsNotNone(next_reminder)
        self.assertEqual(
            next_reminder.due_date,
            timezone.localtime(task.completed_at).date() + timedelta(days=RCH_REMINDER_INTERVAL_DAYS),
        )

    def test_vitals_create_requires_task_edit_capability(self):
        ensure_default_role_settings()
        caller_group, _ = Group.objects.get_or_create(name="Caller")
        caller_user = get_user_model().objects.create_user(username="caller-vitals", password="strong-password-123")
        caller_user.groups.add(caller_group)
        case = Case.objects.create(
            uhid="UH-VITALS-403",
            first_name="Vitals",
            last_name="NoPerm",
            phone_number="9876500198",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        self.client.force_login(caller_user)
        response = self.client.get(reverse("patients:vitals_create", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 403)

    def test_vitals_create_allows_partial_data_and_shows_hb_warning_inline(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-WARN",
            first_name="Vitals",
            last_name="Warn",
            phone_number="9876500199",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        response = self.client.post(
            reverse("patients:vitals_create", kwargs={"pk": case.pk}),
            {
                "recorded_at": timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M"),
                "hemoglobin": "14.2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(VitalEntry.objects.filter(case=case, hemoglobin=Decimal("14.2")).exists())
        self.assertContains(response, "outside expected ANC range")

    def test_vitals_create_rejects_incomplete_bp_pair(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-BP",
            first_name="Vitals",
            last_name="BP",
            phone_number="9876500200",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        response = self.client.post(
            reverse("patients:vitals_create", kwargs={"pk": case.pk}),
            {
                "recorded_at": timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M"),
                "bp_systolic": "120",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(VitalEntry.objects.filter(case=case).exists())
        self.assertContains(response, "Enter diastolic BP")

    def test_vitals_create_returns_json_for_sidebar_ajax(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-AJAX-CREATE",
            first_name="Vitals",
            last_name="AjaxCreate",
            phone_number="9876500200",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:vitals_create", kwargs={"pk": case.pk}),
            {
                "recorded_at": timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M"),
                "bp_systolic": "118",
                "bp_diastolic": "76",
                "pr": "82",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], "Vitals recorded.")
        self.assertEqual(payload["case"]["latest_vitals_snapshot"]["blood_pressure"]["value_display"], "118/76 mmHg")
        self.assertEqual(payload["case"]["recent_vitals_preview"][0]["blood_pressure"]["value_compact"], "118/76")

    def test_vitals_create_returns_json_errors_for_sidebar_ajax(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-AJAX-ERROR",
            first_name="Vitals",
            last_name="AjaxError",
            phone_number="9876500200",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:vitals_create", kwargs={"pk": case.pk}),
            {
                "recorded_at": timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M"),
                "bp_systolic": "120",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["message"], "Could not record vitals. Please check the inputs.")
        self.assertIn("bp_diastolic", payload["errors"])

    def test_vitals_edit_updates_audit_fields(self):
        self.client.force_login(self.user)
        editor = get_user_model().objects.create_user(username="editor", password="strong-password-123")
        doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        editor.groups.add(doctor_group)
        case = Case.objects.create(
            uhid="UH-VITALS-EDIT",
            first_name="Vitals",
            last_name="Edit",
            phone_number="9876500201",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        vital = VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now() - timedelta(hours=1),
            hemoglobin=Decimal("10.5"),
            created_by=self.user,
            updated_by=self.user,
        )

        self.client.force_login(editor)
        response = self.client.post(
            reverse("patients:vitals_edit", kwargs={"pk": vital.pk}),
            {
                "recorded_at": timezone.localtime(vital.recorded_at).strftime("%Y-%m-%dT%H:%M"),
                "hemoglobin": "11.2",
                "pr": "82",
            },
        )

        self.assertEqual(response.status_code, 302)
        vital.refresh_from_db()
        self.assertEqual(vital.updated_by, editor)
        self.assertEqual(vital.hemoglobin, Decimal("11.2"))

    def test_vitals_edit_returns_json_for_sidebar_ajax(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-AJAX-EDIT",
            first_name="Vitals",
            last_name="AjaxEdit",
            phone_number="9876500201",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        vital = VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now(),
            bp_systolic=120,
            bp_diastolic=80,
            pr=78,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("patients:vitals_edit", kwargs={"pk": vital.pk}),
            {
                "recorded_at": timezone.localtime(vital.recorded_at).strftime("%Y-%m-%dT%H:%M"),
                "bp_systolic": "124",
                "bp_diastolic": "82",
                "pr": "84",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], "Vitals updated.")
        vital.refresh_from_db()
        self.assertEqual(vital.bp_systolic, 124)
        self.assertEqual(payload["case"]["latest_vitals_snapshot"]["blood_pressure"]["value_display"], "124/82 mmHg")

    def test_case_detail_renders_vitals_link_and_meta_section(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-DETAIL",
            first_name="Vitals",
            last_name="Detail",
            phone_number="9876500202",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now() - timedelta(days=1),
            bp_systolic=120,
            bp_diastolic=80,
            pr=78,
            spo2=98,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("patients:case_vitals", kwargs={"pk": case.pk}))
        self.assertContains(response, "View Full History")
        self.assertContains(response, "Clinical Details")
        self.assertContains(response, "Vitals")
        self.assertContains(response, "Patient Vitals")
        self.assertContains(response, "Snapshot")
        self.assertContains(response, "Trends")
        self.assertContains(response, "History")
        self.assertContains(response, "Blood Pressure")
        self.assertContains(response, "Elevated")
        self.assertContains(response, "Edit Latest")
        self.assertContains(response, "+ Add")
        self.assertContains(response, "Hemoglobin")
        self.assertNotContains(response, "Latest Snapshot")
        self.assertNotContains(response, "Recent Readings")
        self.assertNotContains(response, "BP Systolic")
        self.assertNotContains(response, "BP Diastolic")

    def test_case_detail_identity_header_preserves_long_name_without_truncation(self):
        self.client.force_login(self.user)
        long_first_name = "Anitha Balasubramanian Lakshmipriya"
        long_last_name = "Subramaniam Narayanaswamy"
        case = Case.objects.create(
            uhid="UH-IDENTITY-LONG-NAME",
            first_name=long_first_name,
            last_name=long_last_name,
            phone_number="9876500211",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, case.full_name)
        self.assertEqual(response.context["case_name_size_class"], "identity-name--compressed")
        self.assertContains(response, "identity-name--compressed")
        self.assertContains(response, "overflow-wrap: normal;")
        self.assertContains(response, "word-break: normal;")
        self.assertContains(response, "grid-template-columns: clamp(25rem, 31vw, 34rem)")

    def test_case_detail_identity_header_renders_redesigned_summary_with_icons(self):
        self.client.force_login(self.user)
        today = timezone.localdate()
        case = Case.objects.create(
            uhid="UH-IDENTITY-HEADER",
            prefix=CasePrefix.MRS,
            first_name="Radha",
            last_name="Patel",
            phone_number="9876500209",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            gender="FEMALE",
            age=28,
            place="Pune",
            referred_by="Dr. Mehra",
            high_risk=True,
            diagnosis="Gestational diabetes mellitus",
            lmp=today - timedelta(days=175),
            edd=today + timedelta(days=105),
            usg_edd=today + timedelta(days=104),
            gravida=2,
            para=1,
            abortions=0,
            living=1,
            anc_high_risk_reasons=[AncHighRiskReason.ANEMIA, AncHighRiskReason.PREVIOUS_LSCS],
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Completed task",
            due_date=today - timedelta(days=3),
            status=TaskStatus.COMPLETED,
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Open task",
            due_date=today + timedelta(days=2),
            status=TaskStatus.SCHEDULED,
            created_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now(),
            bp_systolic=118,
            bp_diastolic=76,
            pr=82,
            spo2=98,
            weight_kg=Decimal("63.4"),
            hemoglobin=Decimal("10.8"),
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["case_initials"], "RP")
        self.assertEqual(response.context["case_name_size_class"], "")
        self.assertContains(response, "Mrs. Radha Patel")
        self.assertEqual(response.context["completed_task_count"], 1)
        self.assertEqual(response.context["total_task_count"], 2)
        self.assertContains(response, "identity-avatar")
        self.assertContains(response, "Task Completion")
        self.assertContains(response, "1 of 2 tasks completed")
        self.assertContains(response, "Clinical Details")
        self.assertContains(response, "Gestational diabetes mellitus")
        self.assertContains(response, "Obstetric Summary")
        self.assertContains(response, "High-risk Reasons")
        self.assertContains(response, "Previous LSCS")
        self.assertContains(response, "#identity-icon-phone")
        self.assertContains(response, "#identity-icon-referral")
        self.assertContains(response, "app-pill high-risk")
        self.assertContains(response, "identity-vitals-panel")
        self.assertNotContains(response, 'class="identity-vitals-card"')
        self.assertContains(response, "Blood Pressure")
        self.assertContains(response, "Patient Vitals")
        self.assertContains(response, "Snapshot")
        self.assertContains(response, "Trends")
        self.assertContains(response, "History")
        self.assertContains(response, "Hemoglobin")
        self.assertNotContains(response, "Latest Snapshot")
        self.assertNotContains(response, "Recent Readings")
        self.assertNotContains(response, "BP Systolic")

    def test_case_detail_identity_header_shows_empty_clinical_state_for_sparse_case(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-IDENTITY-SPARSE",
            first_name="Sparse",
            last_name="Case",
            phone_number="9876500210",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clinical details will appear here as the case record is updated.")
        self.assertContains(response, "0 of 0 tasks completed")

    def test_case_detail_identity_header_shows_zero_gpla_summary(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-IDENTITY-GPLA-ZERO",
            first_name="Zero",
            last_name="GPLA",
            phone_number="9876500211",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            gender=Gender.FEMALE,
            lmp=timezone.localdate() - timedelta(days=56),
            edd=timezone.localdate() + timedelta(days=224),
            rch_bypass=True,
            gravida=0,
            para=0,
            abortions=0,
            living=0,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Obstetric Summary")
        self.assertContains(response, "G0 P0 A0 L0")
        self.assertNotContains(response, "Clinical details will appear here as the case record is updated.")

    def test_case_detail_uses_latest_vitals_timestamp(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-LATEST",
            first_name="Vitals",
            last_name="Latest",
            phone_number="9876500203",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now() - timedelta(hours=1),
            hemoglobin=Decimal("11.2"),
            weight_kg=Decimal("62.0"),
            spo2=98,
            created_by=self.user,
            updated_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now(),
            spo2=96,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        latest_recorded = timezone.localtime(case.vitals.order_by("-recorded_at").first().recorded_at)
        self.assertContains(
            response,
            f"Recorded {latest_recorded.strftime('%d %b %Y')} at {latest_recorded.strftime('%H:%M')}",
        )
        self.assertContains(response, "SpO2")
        self.assertContains(response, "N/A")

    def test_case_detail_no_vitals_shows_add_vitals_text_button(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-EMPTY",
            first_name="Vitals",
            last_name="Empty",
            phone_number="9876500204",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("patients:vitals_create", kwargs={"pk": case.pk}))
        self.assertContains(response, "+ Add")
        self.assertContains(response, reverse("patients:case_vitals", kwargs={"pk": case.pk}))
        self.assertContains(response, "View Full History")
        self.assertContains(response, "Patient Vitals")
        self.assertContains(response, "Snapshot")
        self.assertContains(response, "Trends")
        self.assertContains(response, "History")
        self.assertContains(response, "No vitals have been recorded for this patient yet.")
        self.assertNotContains(response, "No record yet")
        self.assertNotContains(response, "Edit Latest")

    def test_case_detail_removes_lower_vitals_section(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-LOWER-REMOVED",
            first_name="Vitals",
            last_name="Removed",
            phone_number="9876500205",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now(),
            hemoglobin=Decimal("10.2"),
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("patients:case_detail", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Trend (Hemoglobin, Weight, SPO2)")
        self.assertNotContains(response, 'id="vitals-trend-chart"')
        self.assertNotContains(response, 'id="vitals-chart-data"')
        self.assertNotContains(response, "Latest vitals:")
        self.assertNotContains(response, "identity-vitals-strip")

    def test_case_vitals_page_requires_case_access_permission(self):
        locked_user = get_user_model().objects.create_user(username="vitals-locked", password="strong-password-123")
        case = Case.objects.create(
            uhid="UH-VITALS-403-PAGE",
            first_name="Vitals",
            last_name="Denied",
            phone_number="9876500206",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        self.client.force_login(locked_user)
        response = self.client.get(reverse("patients:case_vitals", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 403)

    def test_case_vitals_page_renders_individual_metric_charts(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-CHART-PAGE",
            first_name="Vitals",
            last_name="Charts",
            phone_number="9876500207",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now() - timedelta(hours=2),
            bp_systolic=118,
            bp_diastolic=78,
            pr=72,
            spo2=99,
            weight_kg=Decimal("59.5"),
            hemoglobin=Decimal("10.9"),
            created_by=self.user,
            updated_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now(),
            bp_systolic=124,
            bp_diastolic=82,
            pr=88,
            spo2=97,
            weight_kg=Decimal("60.0"),
            hemoglobin=Decimal("11.4"),
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("patients:case_vitals", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="vitals-chart-blood-pressure"')
        self.assertContains(response, 'id="vitals-chart-pr"')
        self.assertContains(response, 'id="vitals-chart-spo2"')
        self.assertContains(response, 'id="vitals-chart-weight"')
        self.assertContains(response, 'id="vitals-chart-hemoglobin"')
        self.assertContains(response, 'id="vitals-trend-data"')
        self.assertIsNotNone(response.context["vitals_trend_payload"])
        self.assertNotContains(response, 'id="vitals-chart-bp-systolic"')
        self.assertNotContains(response, 'id="vitals-chart-bp-diastolic"')

    def test_case_vitals_page_trend_payload_handles_partial_rows(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-PARTIAL-PAGE",
            first_name="Vitals",
            last_name="Partial",
            phone_number="9876500208",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now() - timedelta(days=1),
            bp_systolic=120,
            hemoglobin=Decimal("9.8"),
            created_by=self.user,
            updated_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now(),
            spo2=97,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("patients:case_vitals", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        payload = response.context["vitals_trend_payload"]
        self.assertEqual(len(payload["labels"]), 2)
        self.assertEqual(payload["datasets"]["blood_pressure"][0]["display"], "120/- mmHg")
        self.assertIsNone(payload["datasets"]["blood_pressure"][0]["range"])
        self.assertEqual(payload["datasets"]["blood_pressure"][1]["display"], "N/A")
        self.assertEqual(payload["datasets"]["hemoglobin"], [9.8, None])
        self.assertEqual(payload["datasets"]["spo2"], [None, 97])

    def test_case_vitals_page_shows_weight_neutral_status(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-VITALS-WEIGHT-NEUTRAL",
            first_name="Vitals",
            last_name="Weight",
            phone_number="9876500209",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        VitalEntry.objects.create(
            case=case,
            recorded_at=timezone.now(),
            weight_kg=Decimal("60.5"),
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("patients:case_vitals", kwargs={"pk": case.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="vitals-status-pill vitals-status-neutral">60.5 kg</span>', html=True)

    def test_case_note_add_does_not_require_task_selection(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH555",
            first_name="No",
            last_name="Task",
            phone_number="9876500011",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )

        response = self.client.post(
            reverse("patients:case_note_create", kwargs={"pk": case.pk}),
            {"note": "Called patient and reviewed instructions."},
        )

        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        latest_log = case.activity_logs.first()
        self.assertIsNotNone(latest_log)
        self.assertEqual(latest_log.note, "Called patient and reviewed instructions.")
        self.assertIsNone(latest_log.task)

    def test_dashboard_groups_tasks_by_patient_and_day(self):
        self.client.force_login(self.user)
        non_surgical, _ = DepartmentConfig.objects.get_or_create(name="Medicine")

        anc_case = Case.objects.create(
            uhid="UH776",
            first_name="ANC",
            last_name="Patient",
            phone_number="9876501110",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=timezone.localdate() - timedelta(days=70),
            edd=timezone.localdate() + timedelta(days=200),
            created_by=self.user,
        )
        case = Case.objects.create(
            uhid="UH777",
            prefix=CasePrefix.MR,
            first_name="Grouped",
            last_name="Patient",
            phone_number="9876501111",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=10),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH778",
            first_name="Medi",
            last_name="Cine",
            phone_number="9876501112",
            category=non_surgical,
            status=CaseStatus.ACTIVE,
            review_date=timezone.localdate() + timedelta(days=15),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH779",
            first_name="ANC",
            last_name="Completed",
            phone_number="9876501113",
            category=self.anc,
            status=CaseStatus.COMPLETED,
            lmp=timezone.localdate() - timedelta(days=60),
            edd=timezone.localdate() + timedelta(days=210),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH780",
            first_name="Surgery",
            last_name="Completed",
            phone_number="9876501114",
            category=self.surgery,
            status=CaseStatus.COMPLETED,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=20),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH781",
            first_name="Medi",
            last_name="Completed",
            phone_number="9876501115",
            category=non_surgical,
            status=CaseStatus.COMPLETED,
            review_date=timezone.localdate() + timedelta(days=25),
            created_by=self.user,
        )
        Task.objects.create(case=anc_case, title="ANC Review", due_date=timezone.localdate(), created_by=self.user)
        Task.objects.create(case=case, title="Lab", due_date=timezone.localdate(), created_by=self.user)
        Task.objects.create(case=case, title="ECG", due_date=timezone.localdate(), created_by=self.user)

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        today_cards = response.context["today_cards"]
        self.assertEqual(len(today_cards), 2)
        self.assertEqual(today_cards[1]["patient_name"], "Mr. Grouped Patient")
        self.assertEqual(today_cards[1]["short_name"], "Grouped P.")
        self.assertEqual(today_cards[1]["task_titles"], ["Lab", "ECG"])
        self.assertEqual(today_cards[1]["due_date_display"], f"{timezone.localdate().strftime('%b')} {timezone.localdate().day}")
        self.assertEqual(today_cards[1]["category_name"], "Surgery")
        self.assertEqual(today_cards[1]["subcategory_name"], "")
        self.assertEqual(today_cards[1]["detail_url"], reverse("patients:case_detail", kwargs={"pk": case.pk}))
        self.assertIn("category_bg_color", today_cards[1])
        self.assertIn("category_text_color", today_cards[1])
        self.assertEqual(today_cards[1]["sex_age"], "-")
        self.assertEqual(response.context["today_date_display"], f"{timezone.localdate().strftime('%b')} {timezone.localdate().day}")
        self.assertEqual(response.context["anc_case_count"], 1)
        self.assertEqual(response.context["surgery_case_count"], 1)
        self.assertEqual(response.context["non_surgical_case_count"], 1)


    def test_dashboard_shows_awaiting_reports_list(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-AWAIT",
            first_name="Awaiting",
            last_name="Patient",
            phone_number="9876503333",
            category=self.surgery,
            subcategory=CaseSubcategory.GENERAL_SURGERY,
            status=CaseStatus.ACTIVE,
            gender=Gender.MALE,
            age=42,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=4),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Upload report",
            due_date=timezone.localdate(),
            status=TaskStatus.AWAITING_REPORTS,
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Awaiting Reports")
        self.assertContains(response, "Upload report")
        self.assertContains(response, "M42")
        self.assertContains(response, 'data-dashboard-module="awaiting"')
        self.assertContains(response, "dashboard-compact-row")
        self.assertContains(response, "data-compact-toggle")
        self.assertContains(response, case.get_subcategory_display())
        self.assertContains(response, "Awaiting Report")
        self.assertContains(response, "Diagnosis :")
        self.assertContains(response, "Due :")
        self.assertContains(response, "Open case")

    def test_dashboard_overdue_module_renders_header_reason_and_open_case_action(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-OVERDUE-DETAIL",
            first_name="Overdue",
            last_name="Detail",
            phone_number="9876504445",
            category=self.surgery,
            subcategory=CaseSubcategory.GENERAL_SURGERY,
            status=CaseStatus.ACTIVE,
            gender=Gender.FEMALE,
            age=33,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=4),
            created_by=self.user,
        )
        Task.objects.create(
            case=case,
            title="Review ultrasound",
            due_date=timezone.localdate() - timedelta(days=2),
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        overdue_section_match = re.search(r'<section[^>]+data-dashboard-module="overdue"[^>]*>.*?</section>', content, re.S)
        self.assertIsNotNone(overdue_section_match)
        section_html = overdue_section_match.group(0)
        self.assertIn(case.get_subcategory_display(), section_html)
        self.assertIn("Reason :", section_html)
        self.assertIn("Review ultrasound", section_html)
        self.assertIn("Open case", section_html)

    def test_dashboard_today_module_renders_header_date_footer_link_and_subcategory_pill(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-TODAY-DETAIL",
            first_name="Today",
            last_name="Detail",
            phone_number="9876504444",
            category=self.surgery,
            subcategory=CaseSubcategory.GENERAL_SURGERY,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=4),
            diagnosis="Thyroid nodule",
            high_risk=True,
            referred_by="PHC",
            ncd_flags=["T2DM"],
            created_by=self.user,
        )
        Task.objects.create(case=case, title="Review", due_date=timezone.localdate(), created_by=self.user)

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        today_section_match = re.search(r'<section[^>]+data-dashboard-module="today"[^>]*>.*?</section>', content, re.S)
        self.assertIsNotNone(today_section_match)
        section_html = today_section_match.group(0)
        today_label = f"Today : {timezone.localdate().strftime('%b')} {timezone.localdate().day}"
        self.assertIn(today_label, section_html)
        self.assertEqual(section_html.count(f"{timezone.localdate().strftime('%b')} {timezone.localdate().day}"), 1)
        self.assertIn(case.get_subcategory_display(), section_html)
        self.assertIn("dashboard-compact-subcategory", section_html)
        self.assertIn("dashboard-compact-details--with-subcategory", section_html)
        self.assertIn("dashboard-compact-detail-line--with-pills", section_html)
        self.assertIn("dashboard-compact-detail-pills", section_html)
        self.assertIn("Diagnosis :", section_html)
        self.assertIn("Tasks :", section_html)
        self.assertIn("dashboard-compact-detail-line", section_html)
        self.assertNotIn("dashboard-compact-detail-block", section_html)
        self.assertIn("High-risk", section_html)
        self.assertIn("Referred by PHC", section_html)
        self.assertIn("T2DM", section_html)
        self.assertIn("dashboard-compact-flag--danger", section_html)
        self.assertIn("dashboard-compact-flag--info", section_html)
        self.assertIn("dashboard-compact-flag--neutral", section_html)
        self.assertIn("&#128222;", section_html)
        self.assertIn("data-call-reveal-trigger", section_html)
        self.assertIn("data-call-reveal-close", section_html)
        self.assertIn("Open case", section_html)
        self.assertContains(response, "external-link-icon.svg")

    def test_dashboard_card_contains_referral_high_risk_and_ncd_flags(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-ICON",
            first_name="Icon",
            last_name="Patient",
            phone_number="9876502222",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=3),
            diagnosis="Thyroid nodule",
            high_risk=True,
            referred_by="PHC",
            ncd_flags=["T2DM", "THYROID"],
            created_by=self.user,
        )
        Task.objects.create(case=case, title="Review", due_date=timezone.localdate(), created_by=self.user)

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        card = response.context["today_cards"][0]
        self.assertTrue(card["high_risk"])
        self.assertEqual(card["referred_by"], "PHC")
        self.assertEqual(card["ncd_flags"], ["T2DM", "THYROID"])


    def test_call_log_summary_resets_failed_counter_after_confirmation(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-CALL-01",
            first_name="Caller",
            last_name="Reset",
            phone_number="9876508888",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=2),
            created_by=self.user,
        )
        Task.objects.create(case=case, title="Follow-up", due_date=timezone.localdate(), created_by=self.user)
        CallLog.objects.create(case=case, outcome=CallOutcome.NO_ANSWER, staff_user=self.user, notes="Attempt 1")
        CallLog.objects.create(case=case, outcome=CallOutcome.CALL_REJECTED, staff_user=self.user, notes="Attempt 2")
        CallLog.objects.create(case=case, outcome=CallOutcome.ANSWERED_CONFIRMED_VISIT, staff_user=self.user, notes="Confirmed")

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        card = response.context["today_cards"][0]
        self.assertEqual(card["call_status"], CallCommunicationStatus.CONFIRMED)
        self.assertEqual(card["failed_attempt_count"], 0)
        self.assertContains(response, "&#128994;&#128222;")

    def test_add_call_log_creates_structured_log_and_activity(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-CALL-02",
            first_name="Call",
            last_name="Create",
            phone_number="9876507777",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=2),
            created_by=self.user,
        )
        task = Task.objects.create(case=case, title="Phone review", due_date=timezone.localdate(), created_by=self.user)

        response = self.client.post(
            reverse("patients:case_call_create", kwargs={"pk": case.id}),
            {"task": task.id, "outcome": CallOutcome.INVALID_NUMBER, "notes": "Wrong number"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(CallLog.objects.filter(case=case, task=task, outcome=CallOutcome.INVALID_NUMBER).exists())
        self.assertTrue(
            case.activity_logs.filter(
                note__icontains="Call outcome logged",
                event_type=ActivityEventType.CALL,
            ).exists()
        )

    def test_create_surgery_case_requires_pathway_and_generates_preop_tasks(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH333",
                "prefix": CasePrefix.MR,
                "first_name": "Surgical",
                "last_name": "Pt",
                "phone_number": "9876500000",
                "category": self.surgery.id,
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
                "status": CaseStatus.ACTIVE,
                "age": "42",
                "surgical_pathway": SurgicalPathway.PLANNED_SURGERY,
                "surgery_date": timezone.localdate() + timedelta(days=7),
            },
        )
        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(uhid="UH333")
        self.assertTrue(case.tasks.filter(title__icontains="Lab test").exists())


    def test_case_autocomplete_requires_authentication(self):
        response = self.client.get(reverse("patients:case_autocomplete"), {"field": "place", "q": "ch"})
        self.assertEqual(response.status_code, 302)

    def test_case_autocomplete_returns_normalized_sorted_suggestions_for_prefix_query(self):
        self.client.force_login(self.user)
        Case.objects.create(
            uhid="UH-AUTO-001",
            first_name="Auto",
            last_name="One",
            phone_number="9000000001",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place=" Chennai  ",
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-AUTO-002",
            first_name="Auto",
            last_name="Two",
            phone_number="9000000002",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place="ChEnnai",
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-AUTO-003",
            first_name="Auto",
            last_name="Three",
            phone_number="9000000003",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place="Coimbatore",
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-AUTO-004",
            first_name="Auto",
            last_name="Four",
            phone_number="9000000004",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place="PHC",
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-AUTO-005",
            first_name="Auto",
            last_name="Five",
            phone_number="9000000005",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place="phc",
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-AUTO-006",
            first_name="Auto",
            last_name="Six",
            phone_number="9000000006",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place="Phc",
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-AUTO-007",
            first_name="Auto",
            last_name="Seven",
            phone_number="9000000007",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place="New   Delhi",
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-AUTO-008",
            first_name="Auto",
            last_name="Eight",
            phone_number="9000000008",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place="  new delhi  ",
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-AUTO-009",
            first_name="Auto",
            last_name="Nine",
            phone_number="9000000009",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place="   ",
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_autocomplete"), {"field": "place", "q": "ch"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["Chennai"])


    def test_case_autocomplete_enforces_minimum_query_length(self):
        self.client.force_login(self.user)
        Case.objects.create(
            uhid="UH-AUTO-MIN-001",
            first_name="Auto",
            last_name="Min",
            phone_number="9010000002",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            place="Chennai",
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_autocomplete"), {"field": "place", "q": "c"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_case_autocomplete_applies_hard_result_cap(self):
        self.client.force_login(self.user)
        for index in range(12):
            Case.objects.create(
                uhid=f"UH-AUTO-CAP-{index:03d}",
                first_name="Auto",
                last_name="Cap",
                phone_number=f"9020000{index:03d}",
                category=self.surgery,
                status=CaseStatus.ACTIVE,
                surgical_pathway=SurgicalPathway.SURVEILLANCE,
                review_date=timezone.localdate() + timedelta(days=5),
                place=f"Alpha City {index}",
                created_by=self.user,
            )

        response = self.client.get(reverse("patients:case_autocomplete"), {"field": "place", "q": "al"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 8)

    def test_case_autocomplete_query_matching_is_case_insensitive_and_space_normalized(self):
        self.client.force_login(self.user)
        Case.objects.create(
            uhid="UH-AUTO-Q-001",
            first_name="Auto",
            last_name="Query",
            phone_number="9010000001",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            diagnosis="Type   2  Diabetes",
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:case_autocomplete"), {"field": "diagnosis", "q": "  TYPE 2   dia "})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["Type 2 Diabetes"])

    def test_case_autocomplete_rejects_invalid_field(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("patients:case_autocomplete"), {"field": "bad_field", "q": "x"})
        self.assertEqual(response.status_code, 400)


    def test_universal_case_search_requires_authentication(self):
        response = self.client.get(reverse("patients:universal_case_search"), {"q": "uh"})
        self.assertEqual(response.status_code, 302)

    def test_case_data_views_require_role_capabilities_for_authenticated_users(self):
        restricted_user = get_user_model().objects.create_user(
            username="restricted",
            password="strong-password-123",
        )
        self.client.force_login(restricted_user)

        dashboard_response = self.client.get(reverse("patients:dashboard"))
        case_list_response = self.client.get(reverse("patients:case_list"))
        autocomplete_response = self.client.get(
            reverse("patients:case_autocomplete"),
            {"field": "place", "q": "ch"},
        )
        universal_search_response = self.client.get(
            reverse("patients:universal_case_search"),
            {"q": "uh"},
        )

        self.assertEqual(dashboard_response.status_code, 403)
        self.assertEqual(case_list_response.status_code, 403)
        self.assertEqual(autocomplete_response.status_code, 403)
        self.assertEqual(universal_search_response.status_code, 403)

    def test_universal_case_search_returns_expected_fields_and_compact_format_data(self):
        self.client.force_login(self.user)
        self.surgery.theme_bg_color = "#abcdef"
        self.surgery.theme_text_color = "#123456"
        self.surgery.save()
        case = Case.objects.create(
            uhid="UH-SEARCH-001",
            first_name="Priya",
            last_name="Sharma",
            phone_number="9012345678",
            category=self.surgery,
            subcategory=CaseSubcategory.ORTHOPEDICS,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=5),
            age=31,
            place="Pune",
            diagnosis="Gallbladder stones",
            high_risk=True,
            referred_by="PHC",
            ncd_flags=["T2DM"],
            created_by=self.user,
        )

        response = self.client.get(reverse("patients:universal_case_search"), {"q": "gall", "category": ["surgical"]})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("results", payload)
        self.assertEqual(len(payload["results"]), 1)
        result = payload["results"][0]
        self.assertEqual(result["uhid"], case.uhid)
        self.assertEqual(result["name"], "Priya Sharma")
        self.assertEqual(result["age"], 31)
        self.assertEqual(result["village"], "Pune")
        self.assertEqual(result["diagnosis"], "Gallbladder stones")
        self.assertEqual(result["subcategory_name"], "Orthopedics")
        self.assertEqual(result["detail_url"], reverse("patients:case_detail", kwargs={"pk": case.pk}))
        category_tag = next(tag for tag in result["tags"] if tag["kind"] == "category")
        subcategory_tag = next(tag for tag in result["tags"] if tag["kind"] == "subcategory")
        self.assertEqual(category_tag["bg_color"], "#abcdef")
        self.assertEqual(category_tag["text_color"], "#123456")
        self.assertEqual(category_tag["border_color"], mix_colors("#abcdef", "#123456", 0.20))
        self.assertEqual(subcategory_tag["label"], "Orthopedics")
        self.assertTrue(any(tag["kind"] == "high_risk" for tag in result["tags"]))
        self.assertTrue(any(tag["kind"] == "referred" for tag in result["tags"]))
        self.assertTrue(any(tag["kind"] == "ncd" for tag in result["tags"]))
        dashboard_response = self.client.get(reverse("patients:dashboard"))
        self.assertContains(dashboard_response, 'data-tag-kind="high_risk"')

    def test_universal_case_search_matches_place_case_notes_and_note_logs_with_direct_results_ranked_first(self):
        self.client.force_login(self.user)
        base_time = timezone.now()

        direct_case = Case.objects.create(
            uhid="UH-SEARCH-PLACE",
            first_name="Direct",
            last_name="Place",
            phone_number="9666666661",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            place="Mango Camp",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )
        case_notes_case = Case.objects.create(
            uhid="UH-SEARCH-CASE-NOTE",
            first_name="Case",
            last_name="Note",
            phone_number="9666666662",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            notes="Mango follow-up note saved in the case summary.",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )
        activity_case = Case.objects.create(
            uhid="UH-SEARCH-ACTIVITY-NOTE",
            first_name="Timeline",
            last_name="Note",
            phone_number="9666666663",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            diagnosis="Routine review",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )
        call_case = Case.objects.create(
            uhid="UH-SEARCH-CALL-NOTE",
            first_name="Call",
            last_name="Note",
            phone_number="9666666664",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            diagnosis="Callback review",
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=6),
            created_by=self.user,
        )
        CaseActivityLog.objects.create(
            case=activity_case,
            user=self.user,
            event_type=ActivityEventType.NOTE,
            note="Mango timeline note recorded after review.",
        )
        CallLog.objects.create(
            case=call_case,
            outcome=CallOutcome.NO_ANSWER,
            notes="Mango call note recorded after outreach attempt.",
            staff_user=self.user,
        )

        Case.objects.filter(pk=direct_case.pk).update(updated_at=base_time - timedelta(days=3))
        Case.objects.filter(pk=case_notes_case.pk).update(updated_at=base_time - timedelta(days=1))
        Case.objects.filter(pk=activity_case.pk).update(updated_at=base_time)
        Case.objects.filter(pk=call_case.pk).update(updated_at=base_time + timedelta(days=1))

        response = self.client.get(
            reverse("patients:universal_case_search"),
            {"q": "mango", "category": ["surgical"]},
        )

        self.assertEqual(response.status_code, 200)
        ordered_ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ordered_ids[:4], [direct_case.id, case_notes_case.id, activity_case.id, call_case.id])

    def test_universal_case_search_applies_multiple_category_filters(self):
        self.client.force_login(self.user)
        non_surgical, _ = DepartmentConfig.objects.get_or_create(name="Medicine")

        anc_case = Case.objects.create(
            uhid="UH-SEARCH-ANC",
            first_name="Anu",
            last_name="Care",
            phone_number="9111111111",
            category=self.anc,
            status=CaseStatus.ACTIVE,
            lmp=timezone.localdate() - timedelta(days=70),
            edd=timezone.localdate() + timedelta(days=200),
            diagnosis="Anemia",
            created_by=self.user,
        )
        surgical_case = Case.objects.create(
            uhid="UH-SEARCH-SURG",
            first_name="Sur",
            last_name="Gery",
            phone_number="9222222222",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            diagnosis="Hernia",
            created_by=self.user,
        )
        Case.objects.create(
            uhid="UH-SEARCH-NS",
            first_name="Medi",
            last_name="Cine",
            phone_number="9333333333",
            category=non_surgical,
            status=CaseStatus.ACTIVE,
            review_date=timezone.localdate() + timedelta(days=10),
            diagnosis="Asthma",
            created_by=self.user,
        )

        response = self.client.get(
            reverse("patients:universal_case_search"),
            {"q": "uh-search", "category": ["anc", "surgical"]},
        )

        self.assertEqual(response.status_code, 200)
        result_ids = {item["id"] for item in response.json()["results"]}
        self.assertIn(anc_case.id, result_ids)
        self.assertIn(surgical_case.id, result_ids)
        self.assertEqual(len(result_ids), 2)

    def test_universal_case_search_orders_by_recent_activity_after_relevance(self):
        self.client.force_login(self.user)
        older_case = Case.objects.create(
            uhid="UH-SEARCH-RECENT-OLD",
            first_name="Recent",
            last_name="Old",
            phone_number="9444444444",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            diagnosis="Kidney stone",
            created_by=self.user,
        )
        newer_case = Case.objects.create(
            uhid="UH-SEARCH-RECENT-NEW",
            first_name="Recent",
            last_name="New",
            phone_number="9555555555",
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            diagnosis="Kidney stone",
            created_by=self.user,
        )
        Case.objects.filter(pk=older_case.pk).update(updated_at=timezone.now() - timedelta(days=3))
        Case.objects.filter(pk=newer_case.pk).update(updated_at=timezone.now())

        response = self.client.get(reverse("patients:universal_case_search"), {"q": "kidney", "category": ["surgical"]})

        self.assertEqual(response.status_code, 200)
        ordered_ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ordered_ids[:2], [newer_case.id, older_case.id])

    def test_authenticated_layout_search_script_includes_full_results_handoff(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View all results")
        self.assertContains(response, reverse("patients:case_list"))
        self.assertContains(response, "category_group")
        self.assertContains(response, "diagnosis / place / case notes / call notes")
        self.assertContains(response, "data-search-category-toggle")
        self.assertContains(response, "data-search-category-menu")
        self.assertContains(response, "data-search-selected-tags")
        self.assertContains(response, 'data-search-category-option="anc"')
        self.assertContains(response, 'data-search-category-option="surgical"')
        self.assertContains(response, 'data-search-category-option="non_surgical"')
        self.assertContains(response, f'data-cases-link-base="{reverse("patients:case_list")}"')
        self.assertNotContains(response, "Limit search and case list shortcuts to selected care pathways.")
        self.assertNotContains(response, "Use the funnel to narrow universal search suggestions and the Cases shortcut without changing the dashboard itself.")


class PatientDataBundleTests(TestCase):
    def setUp(self):
        ensure_default_departments()
        self.user = get_user_model().objects.create_user(username="bundle-owner", password="strong-password-123")
        self.surgery = DepartmentConfig.objects.get(name="Surgery")

    def create_case(self, *, uhid, phone_number):
        return Case.objects.create(
            uhid=uhid,
            first_name="Bundle",
            last_name="Owner",
            phone_number=phone_number,
            category=self.surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )

    def test_patient_data_bundle_manifest_records_sha_and_counts(self):
        case = self.create_case(uhid="UH-BUNDLE-001", phone_number="9555555501")
        task = Task.objects.create(case=case, title="Bundle task", due_date=timezone.localdate(), created_by=self.user)
        VitalEntry.objects.create(case=case, recorded_at=timezone.now(), pr=75, created_by=self.user)
        CaseActivityLog.objects.create(case=case, task=task, user=self.user, note="Bundle activity")
        CallLog.objects.create(case=case, task=task, outcome=CallOutcome.NO_ANSWER, staff_user=self.user)

        archive_bytes, manifest, filename = database_bundle.create_bundle_archive()

        self.assertTrue(filename.startswith("patient-data-bundle-"))
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as bundle_zip:
            patient_data_bytes = bundle_zip.read(database_bundle.PATIENT_DATA_FILENAME)
            payload = json.loads(patient_data_bytes.decode("utf-8"))
        self.assertEqual(manifest["counts"], database_bundle.compute_payload_counts(payload))
        self.assertEqual(manifest["patient_data_sha256"], hashlib.sha256(patient_data_bytes).hexdigest())
        self.assertEqual(payload["cases"][0]["uhid"], "UH-BUNDLE-001")

    def test_patient_data_bundle_round_trips_subcategory_and_accepts_legacy_payloads_without_it(self):
        Case.objects.create(
            uhid="UH-BUNDLE-SUBCATEGORY",
            prefix=CasePrefix.MRS,
            first_name="Bundle",
            last_name="Subcategory",
            phone_number="9555555599",
            category=self.surgery,
            subcategory=CaseSubcategory.ORTHOPEDICS,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        Case.objects.create(
            uhid="QE-BUNDLE-001",
            prefix=CasePrefix.MS,
            first_name="Quick",
            last_name="",
            phone_number="",
            alternate_phone_number="",
            category=self.surgery,
            subcategory="",
            status=CaseStatus.ACTIVE,
            review_date=timezone.localdate() + timedelta(days=5),
            diagnosis="Quick entry pending details",
            metadata={"entry_mode": "quick_entry", "details_pending": True},
            created_by=self.user,
        )

        archive_bytes, _, _ = database_bundle.create_bundle_archive()
        import_result = database_bundle.import_bundle_bytes(archive_bytes)
        self.assertEqual(import_result["counts"]["cases"], 2)
        restored_case = Case.objects.get(uhid="UH-BUNDLE-SUBCATEGORY")
        self.assertEqual(restored_case.prefix, CasePrefix.MRS)
        self.assertEqual(restored_case.subcategory, CaseSubcategory.ORTHOPEDICS)
        quick_entry_case = Case.objects.get(uhid="QE-BUNDLE-001")
        self.assertEqual(quick_entry_case.prefix, CasePrefix.MS)
        self.assertEqual(quick_entry_case.subcategory, "")

        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as bundle_zip:
            payload = json.loads(bundle_zip.read(database_bundle.PATIENT_DATA_FILENAME).decode("utf-8"))
            manifest = json.loads(bundle_zip.read(database_bundle.MANIFEST_FILENAME).decode("utf-8"))

        for case_payload in payload["cases"]:
            if case_payload.get("uhid") == "UH-BUNDLE-SUBCATEGORY":
                case_payload.pop("subcategory", None)
            case_payload.pop("prefix", None)
        patient_data_bytes = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
        manifest["counts"] = database_bundle.compute_payload_counts(payload)
        manifest["patient_data_sha256"] = hashlib.sha256(patient_data_bytes).hexdigest()

        legacy_archive = io.BytesIO()
        with zipfile.ZipFile(legacy_archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle_zip:
            bundle_zip.writestr(database_bundle.PATIENT_DATA_FILENAME, patient_data_bytes)
            bundle_zip.writestr(
                database_bundle.MANIFEST_FILENAME,
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8"),
            )

        database_bundle.import_bundle_bytes(legacy_archive.getvalue())
        legacy_case = Case.objects.get(uhid="UH-BUNDLE-SUBCATEGORY")
        self.assertEqual(legacy_case.prefix, "")
        self.assertEqual(legacy_case.subcategory, CaseSubcategory.GENERAL_SURGERY)
        legacy_quick_entry_case = Case.objects.get(uhid="QE-BUNDLE-001")
        self.assertEqual(legacy_quick_entry_case.prefix, "")
        self.assertEqual(legacy_quick_entry_case.subcategory, "")

    def test_backup_patient_data_command_prunes_old_backups(self):
        self.create_case(uhid="UH-BUNDLE-002", phone_number="9555555502")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            for suffix in ("20240101-000000-000000Z", "20240102-000000-000000Z", "20240103-000000-000000Z"):
                (temp_path / f"patient-data-bundle-manual-{suffix}.zip").write_bytes(b"old")

            stdout = io.StringIO()
            call_command("backup_patient_data", "--output-dir", temp_dir, "--keep", "2", stdout=stdout)

            remaining = sorted(temp_path.glob("patient-data-bundle-manual-*.zip"))
            self.assertEqual(len(remaining), 2)
            self.assertIn("Created patient-data backup", stdout.getvalue())

    def test_prune_backup_bundles_only_removes_matching_backup_kind(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            for filename in (
                "patient-data-bundle-daily-20240101-000000-000000Z.zip",
                "patient-data-bundle-daily-20240102-000000-000000Z.zip",
                "patient-data-bundle-daily-20240103-000000-000000Z.zip",
                "patient-data-bundle-monthly-20240101-000000-000000Z.zip",
                "patient-data-bundle-yearly-20240101-000000-000000Z.zip",
            ):
                (temp_path / filename).write_bytes(b"old")

            database_bundle.prune_backup_bundles(temp_path, keep=2, backup_kind=database_bundle.BACKUP_KIND_DAILY)

            self.assertEqual(len(list(temp_path.glob("patient-data-bundle-daily-*.zip"))), 2)
            self.assertEqual(len(list(temp_path.glob("patient-data-bundle-monthly-*.zip"))), 1)
            self.assertEqual(len(list(temp_path.glob("patient-data-bundle-yearly-*.zip"))), 1)


class SeedMockDataCommandTests(TestCase):
    def _seeded_vitals_snapshot(self):
        snapshot = {}
        for case in Case.objects.filter(metadata__source="seed_mock_data").order_by("uhid"):
            rows = []
            for vital in case.vitals.order_by("recorded_at", "id"):
                rows.append(
                    (
                        timezone.localtime(vital.recorded_at).strftime("%Y-%m-%d %H:%M"),
                        vital.bp_systolic,
                        vital.bp_diastolic,
                        vital.pr,
                        vital.spo2,
                        str(vital.weight_kg),
                        str(vital.hemoglobin) if vital.hemoglobin is not None else None,
                    )
                )
            snapshot[case.uhid] = rows
        return snapshot

    def test_seed_mock_data_creates_deterministic_scenarios_and_related_records(self):
        call_command(
            "seed_mock_data",
            "--count",
            "30",
            "--reset",
            "--include-rch-scenarios",
            "--include-vitals",
        )

        seeded_cases = Case.objects.filter(metadata__source="seed_mock_data").order_by("uhid")
        self.assertEqual(seeded_cases.count(), 30)

        for case in seeded_cases:
            self.assertTrue(case.prefix)
            self.assertTrue(case.gender)
            self.assertIsNotNone(case.age)
            self.assertTrue(case.diagnosis)
            self.assertTrue(case.metadata.get("seed_scenario"))
            if case.metadata.get("entry_mode") == "quick_entry":
                self.assertRegex(case.uhid, r"^QE-\d{8}-\d{3}$")
                self.assertEqual(case.phone_number, "")
                self.assertEqual(case.alternate_phone_number, "")
                self.assertEqual(case.place, "")
                self.assertEqual(case.referred_by, "")
                continue
            self.assertRegex(case.uhid, r"^TN-[A-Z]{3}-\d{6}$")
            self.assertRegex(case.phone_number, r"^[6-9]\d{9}$")
            self.assertRegex(case.alternate_phone_number, r"^[6-9]\d{9}$")
            self.assertIsNotNone(case.date_of_birth)
            self.assertTrue(case.place)
            self.assertTrue(case.referred_by)

        anc_high_risk = seeded_cases.get(metadata__seed_scenario="anc_high_risk")
        self.assertTrue(anc_high_risk.high_risk)
        self.assertTrue(anc_high_risk.anc_high_risk_reasons)
        self.assertTrue(anc_high_risk.rch_number)
        self.assertFalse(anc_high_risk.rch_bypass)

        anc_rch_missing = seeded_cases.get(metadata__seed_scenario="anc_rch_missing")
        self.assertFalse(anc_rch_missing.rch_number)
        self.assertTrue(anc_rch_missing.rch_bypass)

        surgery_cases = seeded_cases.filter(category__name="Surgery")
        self.assertTrue(surgery_cases.filter(surgical_pathway=SurgicalPathway.PLANNED_SURGERY).exists())
        self.assertTrue(surgery_cases.filter(surgical_pathway=SurgicalPathway.SURVEILLANCE).exists())
        typed_surgery_cases = [case for case in surgery_cases if case.metadata.get("entry_mode") != "quick_entry"]
        self.assertTrue(typed_surgery_cases)
        self.assertTrue(all(case.subcategory for case in typed_surgery_cases))
        self.assertGreaterEqual(len({case.subcategory for case in typed_surgery_cases}), 2)

        non_surgical_cases = seeded_cases.filter(category__name="Medicine")
        self.assertGreaterEqual(non_surgical_cases.values("review_frequency").distinct().count(), 3)
        typed_non_surgical_cases = [case for case in non_surgical_cases if case.metadata.get("entry_mode") != "quick_entry"]
        self.assertTrue(typed_non_surgical_cases)
        self.assertTrue(all(case.subcategory for case in typed_non_surgical_cases))
        self.assertGreaterEqual(len({case.subcategory for case in typed_non_surgical_cases}), 2)

        quick_entry_case = seeded_cases.get(metadata__seed_scenario="quick_entry_pending_details")
        self.assertTrue(quick_entry_case.prefix)
        self.assertEqual(quick_entry_case.metadata.get("entry_mode"), "quick_entry")
        self.assertTrue(quick_entry_case.metadata.get("details_pending"))
        self.assertEqual(quick_entry_case.subcategory, "")
        self.assertTrue(quick_entry_case.tasks.filter(title=QUICK_ENTRY_DETAILS_TASK_TITLE).exists())

        self.assertTrue(Task.objects.filter(case=anc_high_risk, status=TaskStatus.AWAITING_REPORTS).exists())
        self.assertTrue(Task.objects.filter(case=anc_high_risk, status=TaskStatus.COMPLETED).exists())
        self.assertTrue(Task.objects.filter(case=anc_high_risk, due_date__lt=timezone.localdate()).exists())
        self.assertTrue(Task.objects.filter(case=anc_high_risk, due_date__gt=timezone.localdate()).exists())

        self.assertEqual(VitalEntry.objects.filter(case=anc_high_risk).count(), 6)
        self.assertTrue(CallLog.objects.filter(case=anc_high_risk, task__isnull=False).exists())
        self.assertTrue(CallLog.objects.filter(case=anc_high_risk, task__isnull=True).exists())

    def test_seed_mock_data_smoke_profile_defaults_to_small_case_count(self):
        call_command("seed_mock_data", "--profile", "smoke", "--reset")

        self.assertEqual(Case.objects.filter(metadata__source="seed_mock_data").count(), 12)

    def test_seed_mock_data_reset_keeps_non_seeded_cases(self):
        ensure_default_departments()
        surgery = DepartmentConfig.objects.get(name="Surgery")
        user = get_user_model().objects.create_user(username="manual_case_owner")

        non_seeded_case = Case.objects.create(
            uhid="UH-MANUAL-0001",
            first_name="Manual",
            last_name="Patient",
            phone_number="9888888888",
            category=surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            diagnosis="Follow-up",
            created_by=user,
            metadata={"source": "manual_entry"},
        )
        CallLog.objects.create(case=non_seeded_case, outcome=CallOutcome.NO_ANSWER, notes="manual", staff_user=user)
        CaseActivityLog.objects.create(case=non_seeded_case, user=user, note="manual activity")

        call_command("seed_mock_data", "--count", "3")
        seeded_ids = list(Case.objects.filter(metadata__source="seed_mock_data").values_list("id", flat=True))

        self.assertTrue(seeded_ids)
        self.assertTrue(CallLog.objects.filter(case_id__in=seeded_ids).exists())
        self.assertTrue(CaseActivityLog.objects.filter(case_id__in=seeded_ids).exists())

        call_command("seed_mock_data", "--count", "2", "--reset")

        non_seeded_case.refresh_from_db()
        self.assertEqual(non_seeded_case.metadata.get("source"), "manual_entry")
        self.assertTrue(CallLog.objects.filter(case=non_seeded_case).exists())
        self.assertTrue(CaseActivityLog.objects.filter(case=non_seeded_case).exists())
        self.assertEqual(Case.objects.filter(metadata__source="seed_mock_data").count(), 2)

    @patch("patients.management.commands.seed_mock_data.sys.stdin.isatty", return_value=False)
    def test_seed_mock_data_reset_all_requires_yes_flag_in_non_interactive_mode(self, _isatty_mock):
        ensure_default_departments()
        surgery = DepartmentConfig.objects.get(name="Surgery")
        user = get_user_model().objects.create_user(username="reset-all-owner")
        Case.objects.create(
            uhid="UH-RESET-ALL-001",
            first_name="Keep",
            last_name="Me",
            phone_number="9777777777",
            category=surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=9),
            created_by=user,
            metadata={"source": "manual_entry"},
        )

        with self.assertRaises(CommandError):
            call_command("seed_mock_data", "--count", "2", "--reset-all")

        self.assertTrue(Case.objects.filter(uhid="UH-RESET-ALL-001").exists())

    @patch("patients.management.commands.seed_mock_data.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="no")
    def test_seed_mock_data_reset_all_prompt_aborts_when_not_confirmed(self, _input_mock, _isatty_mock):
        ensure_default_departments()
        surgery = DepartmentConfig.objects.get(name="Surgery")
        user = get_user_model().objects.create_user(username="interactive-reset-owner")
        Case.objects.create(
            uhid="UH-RESET-ALL-002",
            first_name="Abort",
            last_name="Reset",
            phone_number="9666666666",
            category=surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=8),
            created_by=user,
            metadata={"source": "manual_entry"},
        )

        with self.assertRaises(CommandError):
            call_command("seed_mock_data", "--count", "2", "--reset-all")

        self.assertTrue(Case.objects.filter(uhid="UH-RESET-ALL-002").exists())

    def test_seed_mock_data_reset_all_with_yes_flag_wipes_and_reseeds(self):
        ensure_default_departments()
        surgery = DepartmentConfig.objects.get(name="Surgery")
        user = get_user_model().objects.create_user(username="wipe-reset-owner")
        Case.objects.create(
            uhid="UH-RESET-ALL-003",
            first_name="Wipe",
            last_name="Me",
            phone_number="9555555555",
            category=surgery,
            status=CaseStatus.ACTIVE,
            surgical_pathway=SurgicalPathway.SURVEILLANCE,
            review_date=timezone.localdate() + timedelta(days=7),
            created_by=user,
            metadata={"source": "manual_entry"},
        )

        call_command("seed_mock_data", "--profile", "smoke", "--count", "2", "--reset-all", "--yes-reset-all")

        self.assertFalse(Case.objects.filter(uhid="UH-RESET-ALL-003").exists())
        self.assertEqual(Case.objects.filter(metadata__source="seed_mock_data").count(), 2)

    def test_seed_mock_data_vitals_density_is_profile_based_for_all_seeded_cases(self):
        call_command("seed_mock_data", "--profile", "smoke", "--count", "4", "--include-vitals", "--reset")

        smoke_cases = Case.objects.filter(metadata__source="seed_mock_data").order_by("uhid")
        self.assertEqual(smoke_cases.count(), 4)
        for case in smoke_cases:
            self.assertEqual(VitalEntry.objects.filter(case=case).count(), 4)

        call_command("seed_mock_data", "--profile", "full", "--count", "4", "--include-vitals", "--reset")

        full_cases = Case.objects.filter(metadata__source="seed_mock_data").order_by("uhid")
        self.assertEqual(full_cases.count(), 4)
        for case in full_cases:
            self.assertEqual(VitalEntry.objects.filter(case=case).count(), 6)

    def test_seed_mock_data_vitals_align_with_past_relevant_task_dates_and_no_future_rows(self):
        call_command(
            "seed_mock_data",
            "--profile",
            "smoke",
            "--count",
            "6",
            "--include-vitals",
            "--include-rch-scenarios",
            "--reset",
        )

        now = timezone.now()
        today = timezone.localdate()
        relevant_task_types = [TaskType.LAB, TaskType.VISIT, TaskType.PROCEDURE]
        seeded_cases = Case.objects.filter(metadata__source="seed_mock_data").order_by("uhid")
        for case in seeded_cases:
            vitals = list(case.vitals.order_by("recorded_at", "id"))
            self.assertEqual(len(vitals), 4)
            for vital in vitals:
                self.assertLessEqual(vital.recorded_at, now)
            vital_days = {timezone.localtime(vital.recorded_at).date() for vital in vitals}
            past_task_days = set(
                case.tasks.filter(task_type__in=relevant_task_types, due_date__lte=today).values_list("due_date", flat=True)
            )
            self.assertTrue(vital_days.intersection(past_task_days))

    def test_seed_mock_data_vitals_are_deterministic_across_reset_runs(self):
        call_command("seed_mock_data", "--profile", "full", "--count", "8", "--include-vitals", "--reset")
        snapshot_first = self._seeded_vitals_snapshot()

        call_command("seed_mock_data", "--profile", "full", "--count", "8", "--include-vitals", "--reset")
        snapshot_second = self._seeded_vitals_snapshot()

        self.assertEqual(snapshot_first, snapshot_second)


class LoginPageVersionTests(TestCase):
    def test_login_page_displays_current_app_version(self):
        response = self.client.get(reverse("login"))
        app_version = Path("VERSION").read_text(encoding="utf-8").strip()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Version {app_version}")
