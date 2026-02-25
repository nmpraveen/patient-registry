from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import CaseForm
from .models import Case, CaseStatus, DepartmentConfig, RoleSetting, SurgicalPathway, Task, TaskStatus, ensure_default_role_settings


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


class MedtrackViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="doc", password="strong-password-123")
        doctor_group, _ = Group.objects.get_or_create(name="Doctor")
        self.user.groups.add(doctor_group)

        self.anc, _ = DepartmentConfig.objects.get_or_create(name="ANC")
        self.surgery, _ = DepartmentConfig.objects.get_or_create(name="Surgery")

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
        Task.objects.create(case=case, title="Lab", due_date=timezone.localdate(), created_by=self.user)
        Task.objects.create(case=case, title="ECG", due_date=timezone.localdate(), created_by=self.user)

        response = self.client.get(reverse("patients:dashboard"))

        self.assertEqual(response.status_code, 200)
        today_cards = response.context["today_cards"]
        self.assertEqual(len(today_cards), 1)
        self.assertEqual(today_cards[0]["patient_name"], "Grouped Patient")
        self.assertEqual(today_cards[0]["task_titles"], ["Lab", "ECG"])


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

    def test_case_autocomplete_returns_normalized_frequency_sorted_suggestions(self):
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

        response = self.client.get(reverse("patients:case_autocomplete"), {"field": "place", "q": ""})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"text": "PHC", "count": 3},
                {"text": "Chennai", "count": 2},
                {"text": "New Delhi", "count": 2},
                {"text": "Coimbatore", "count": 1},
            ],
        )

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
        self.assertEqual(response.json(), [{"text": "Type 2 Diabetes", "count": 1}])

    def test_case_autocomplete_rejects_invalid_field(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("patients:case_autocomplete"), {"field": "bad_field", "q": "x"})
        self.assertEqual(response.status_code, 400)


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
