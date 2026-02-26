from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .forms import CaseForm
from .models import CallCommunicationStatus, CallLog, CallOutcome, Case, CaseStatus, DepartmentConfig, RoleSetting, SurgicalPathway, Task, TaskStatus, ensure_default_role_settings


class MedtrackModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="doctor", password="pw12345")
        self.anc, _ = DepartmentConfig.objects.get_or_create(name="ANC", defaults={"predefined_actions": ["USG"], "metadata_template": {"lmp": "date"}})

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


class MedtrackViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="doc", password="strong-password-123")
        doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        self.user.groups.add(doctor_group)

        self.anc, _ = DepartmentConfig.objects.get_or_create(name="ANC")
        self.surgery, _ = DepartmentConfig.objects.get_or_create(name="Surgery")

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

    def test_dashboard_query_count_stays_bounded(self):
        self.client.force_login(self.user)
        non_surgical, _ = DepartmentConfig.objects.get_or_create(name="Non Surgical")
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

        response = self.assert_max_queries(8, reverse("patients:dashboard"), {"upcoming_days": 14})

        self.assertEqual(response.context["anc_case_count"], 1)
        self.assertEqual(response.context["surgery_case_count"], 1)
        self.assertEqual(response.context["non_surgical_case_count"], 1)

    def test_create_anc_case_autogenerates_tasks(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH222",
                "first_name": "Grace",
                "last_name": "Hopper",
                "phone_number": "9876543210",
                "category": self.anc.id,
                "status": CaseStatus.ACTIVE,
                "age": "28",
                "lmp": timezone.localdate() - timedelta(days=60),
                "edd": timezone.localdate() + timedelta(days=210),
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(uhid="UH222")
        self.assertGreaterEqual(case.tasks.count(), 20)

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

    def test_dashboard_invalid_upcoming_days_defaults_to_seven(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:dashboard"), {"upcoming_days": "invalid"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["upcoming_days"], 7)


    def test_case_form_bootstraps_categories_when_empty(self):
        DepartmentConfig.objects.all().delete()
        self.client.force_login(self.user)
        response = self.client.get(reverse("patients:case_create"))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(DepartmentConfig.objects.count(), 3)


    def test_admin_settings_page_access_and_role_config(self):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)
        response = self.client.get(reverse("patients:settings"))
        self.assertEqual(response.status_code, 200)
        post_response = self.client.post(
            reverse("patients:settings"),
            {
                "action": "create_role",
                "role_name": "Reception",
                "can_case_create": "on",
                "can_case_edit": "on",
                "can_task_create": "on",
                "can_note_add": "on",
            },
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertTrue(RoleSetting.objects.filter(role_name="Reception").exists())


    def test_create_case_saves_gender_dob_and_place(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH444",
                "first_name": "Asha",
                "last_name": "Devi",
                "gender": "FEMALE",
                "date_of_birth": "1995-01-15",
                "place": "Chennai",
                "phone_number": "9123456789",
                "category": self.surgery.id,
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

    def test_case_form_uses_dob_to_calculate_age(self):
        dob = timezone.localdate() - timedelta(days=365 * 25)
        form = CaseForm(
            data={
                "uhid": "UH-AGE1",
                "first_name": "Age",
                "last_name": "Auto",
                "phone_number": "9876500077",
                "category": self.surgery.id,
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

    def test_case_form_requires_age_when_dob_missing(self):
        form = CaseForm(
            data={
                "uhid": "UH-AGE2",
                "first_name": "Age",
                "last_name": "Manual",
                "phone_number": "9876500078",
                "category": self.surgery.id,
                "status": CaseStatus.ACTIVE,
                "surgical_pathway": SurgicalPathway.SURVEILLANCE,
                "review_date": (timezone.localdate() + timedelta(days=10)).isoformat(),
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("age", form.errors)


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
        non_surgical, _ = DepartmentConfig.objects.get_or_create(name="Non Surgical")

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
            first_name="Non",
            last_name="Surgical",
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
            first_name="Non",
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
        self.assertEqual(today_cards[1]["patient_name"], "Grouped Patient")
        self.assertEqual(today_cards[1]["task_titles"], ["Lab", "ECG"])
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
            status=CaseStatus.ACTIVE,
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
        self.assertTrue(case.activity_logs.filter(note__icontains="Call outcome logged").exists())

    def test_create_surgery_case_requires_pathway_and_generates_preop_tasks(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH333",
                "first_name": "Surgical",
                "last_name": "Pt",
                "phone_number": "9876500000",
                "category": self.surgery.id,
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

    def test_universal_case_search_returns_expected_fields_and_compact_format_data(self):
        self.client.force_login(self.user)
        case = Case.objects.create(
            uhid="UH-SEARCH-001",
            first_name="Priya",
            last_name="Sharma",
            phone_number="9012345678",
            category=self.surgery,
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
        self.assertEqual(result["detail_url"], reverse("patients:case_detail", kwargs={"pk": case.pk}))
        self.assertTrue(any(tag["kind"] == "category" for tag in result["tags"]))
        self.assertTrue(any(tag["kind"] == "high_risk" for tag in result["tags"]))
        self.assertTrue(any(tag["kind"] == "referred" for tag in result["tags"]))
        self.assertTrue(any(tag["kind"] == "ncd" for tag in result["tags"]))

    def test_universal_case_search_applies_multiple_category_filters(self):
        self.client.force_login(self.user)
        non_surgical, _ = DepartmentConfig.objects.get_or_create(name="Non Surgical")

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
            first_name="Non",
            last_name="Surg",
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


class SeedMockDataCommandTests(TestCase):
    def test_seed_mock_data_creates_cases_with_believable_identifiers_and_new_fields(self):
        call_command("seed_mock_data", "--count", "30", "--reset")

        seeded_cases = Case.objects.filter(uhid__startswith="TN-").order_by("uhid")
        self.assertEqual(seeded_cases.count(), 30)

        for case in seeded_cases:
            self.assertRegex(case.uhid, r"^TN-[A-Z]{3}-\d{6}$")
            self.assertRegex(case.phone_number, r"^[6-9]\d{9}$")
            self.assertRegex(case.alternate_phone_number, r"^[6-9]\d{9}$")
            self.assertTrue(case.gender)
            self.assertIsNotNone(case.date_of_birth)
            self.assertTrue(case.place)
            self.assertIsNotNone(case.age)
            self.assertTrue(case.diagnosis)
            self.assertTrue(case.referred_by)

        anc_cases = seeded_cases.filter(category__name="ANC")
        self.assertFalse(anc_cases.filter(gender="MALE").exists())
        self.assertTrue(anc_cases.filter(gravida__isnull=False, para__isnull=False, abortions__isnull=False, living__isnull=False).exists())

        surgery_cases = seeded_cases.filter(category__name="Surgery")
        self.assertTrue(surgery_cases.filter(surgical_pathway=SurgicalPathway.PLANNED_SURGERY).exists())
        self.assertTrue(surgery_cases.filter(surgical_pathway=SurgicalPathway.SURVEILLANCE).exists())

        non_surgical_cases = seeded_cases.filter(category__name="Non Surgical")
        self.assertGreaterEqual(non_surgical_cases.values("review_frequency").distinct().count(), 3)
