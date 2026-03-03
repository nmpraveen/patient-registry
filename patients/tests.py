from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .forms import CaseForm
from .models import (
    AncHighRiskReason,
    CallCommunicationStatus,
    CallLog,
    CallOutcome,
    Case,
    CaseActivityLog,
    CaseStatus,
    DepartmentConfig,
    RCH_REMINDER_INTERVAL_DAYS,
    RCH_REMINDER_TASK_TITLE,
    RoleSetting,
    SurgicalPathway,
    Task,
    TaskStatus,
    VitalEntry,
    ensure_default_departments,
    ensure_default_role_settings,
)


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

    def test_case_list_category_group_filter_matches_dashboard_buckets(self):
        self.client.force_login(self.user)
        non_surgical_hyphen, _ = DepartmentConfig.objects.get_or_create(name="Non-Surgical")
        non_surgical_space, _ = DepartmentConfig.objects.get_or_create(name="Non Surgical")
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
            first_name="Non",
            last_name="Space",
            phone_number="8123000005",
            category=non_surgical_space,
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

    def test_dashboard_category_cards_link_to_active_case_filters(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "?status=ACTIVE&category_group=anc")
        self.assertContains(response, "?status=ACTIVE&category_group=surgery")
        self.assertContains(response, "?status=ACTIVE&category_group=non_surgical")

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
                "rch_bypass": "on",
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

    def test_case_detail_task_table_replaces_freq_with_completed_on(self):
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
        self.assertContains(response, '<th class="d-none d-md-table-cell">Completed On</th>', html=True)
        self.assertNotContains(response, '<th class="d-none d-md-table-cell">Freq</th>', html=True)

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
        self.assertContains(
            response,
            f'<td class="d-none d-md-table-cell">{expected_date}</td>',
            html=True,
        )

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
        self.assertContains(
            response,
            f'<td class="d-none d-md-table-cell">{due_date.strftime("%d-%m-%y")}</td>',
            html=True,
        )

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
        self.assertContains(response, '<td class="d-none d-md-table-cell">-</td>', html=True)

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



    def test_admin_settings_page_shows_changelog_link(self):
        ensure_default_role_settings()
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.user.groups.clear()
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

        response = self.client.get(reverse("patients:settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("patients:changelog"))

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

    def test_case_form_requires_anc_high_risk_reasons_when_high_risk_checked(self):
        form = CaseForm(
            data={
                "uhid": "UH-HR-ANC-1",
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

    def test_case_detail_renders_vitals_summary_card_as_fifth_box(self):
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
        self.assertContains(response, "Open vitals trends")
        self.assertEqual(response.content.decode().count('class="case-summary-card'), 5)

    def test_case_detail_uses_latest_row_and_na_for_missing_vitals(self):
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
        self.assertContains(response, "96 %")
        self.assertContains(response, "N/A")
        self.assertNotContains(response, "11.2 g/dL")

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
        self.assertContains(response, "Add Vitals")
        self.assertNotContains(response, "Open vitals trends")

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
        self.assertContains(response, 'id="vitals-chart-bp-systolic"')
        self.assertContains(response, 'id="vitals-chart-bp-diastolic"')
        self.assertContains(response, 'id="vitals-chart-pr"')
        self.assertContains(response, 'id="vitals-chart-spo2"')
        self.assertContains(response, 'id="vitals-chart-weight"')
        self.assertContains(response, 'id="vitals-chart-hemoglobin"')
        self.assertContains(response, 'id="vitals-trend-data"')
        self.assertIsNotNone(response.context["vitals_trend_payload"])

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
            self.assertRegex(case.uhid, r"^TN-[A-Z]{3}-\d{6}$")
            self.assertRegex(case.phone_number, r"^[6-9]\d{9}$")
            self.assertRegex(case.alternate_phone_number, r"^[6-9]\d{9}$")
            self.assertTrue(case.gender)
            self.assertIsNotNone(case.date_of_birth)
            self.assertTrue(case.place)
            self.assertIsNotNone(case.age)
            self.assertTrue(case.diagnosis)
            self.assertTrue(case.referred_by)
            self.assertTrue(case.metadata.get("seed_scenario"))

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

        non_surgical_cases = seeded_cases.filter(category__name="Non Surgical")
        self.assertGreaterEqual(non_surgical_cases.values("review_frequency").distinct().count(), 3)

        self.assertTrue(Task.objects.filter(case=anc_high_risk, status=TaskStatus.AWAITING_REPORTS).exists())
        self.assertTrue(Task.objects.filter(case=anc_high_risk, status=TaskStatus.COMPLETED).exists())
        self.assertTrue(Task.objects.filter(case=anc_high_risk, due_date__lt=timezone.localdate()).exists())
        self.assertTrue(Task.objects.filter(case=anc_high_risk, due_date__gt=timezone.localdate()).exists())

        self.assertGreaterEqual(VitalEntry.objects.filter(case=anc_high_risk).count(), 1)
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


class LoginPageVersionTests(TestCase):
    def test_login_page_displays_current_app_version(self):
        response = self.client.get(reverse("login"))
        app_version = Path("VERSION").read_text(encoding="utf-8").strip()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Version {app_version}")
