from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Case, CaseStatus, DepartmentConfig, Task, TaskStatus


class MedtrackModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="doctor", password="pw12345")
        self.department = DepartmentConfig.objects.create(name="ANC", predefined_actions=["USG"], metadata_template={"lmp": "date"})

    def test_case_phone_validation(self):
        case = Case(
            uhid="UH001",
            patient_name="Jane Doe",
            phone_number="12345",
            category=self.department,
            created_by=self.user,
        )
        with self.assertRaises(Exception):
            case.full_clean()

    def test_task_completion_sets_completed_at(self):
        case = Case.objects.create(uhid="UH100", patient_name="A", phone_number="9999999999", category=self.department, created_by=self.user)
        task = Task.objects.create(case=case, title="Lab", due_date=timezone.localdate(), created_by=self.user)
        self.assertIsNone(task.completed_at)
        task.status = TaskStatus.COMPLETED
        task.save()
        self.assertIsNotNone(task.completed_at)


class MedtrackViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="staff", password="strong-password-123")
        self.department = DepartmentConfig.objects.create(name="Surgery")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("patients:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_create_case_and_task(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:case_create"),
            {
                "uhid": "UH222",
                "patient_name": "Grace Hopper",
                "phone_number": "9876543210",
                "category": self.department.id,
                "status": CaseStatus.ACTIVE,
                "metadata": "{}",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        case = Case.objects.get(uhid="UH222")

        task_response = self.client.post(
            reverse("patients:task_create", kwargs={"pk": case.id}),
            {
                "title": "Follow-up call",
                "due_date": timezone.localdate() + timedelta(days=1),
                "status": TaskStatus.SCHEDULED,
                "task_type": "CALL",
                "notes": "",
            },
        )
        self.assertEqual(task_response.status_code, 302)
        self.assertEqual(case.tasks.count(), 1)
