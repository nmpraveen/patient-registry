from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Patient


class PatientModelTests(TestCase):
    def test_create_patient_model(self):
        patient = Patient.objects.create(first_name="Ada", last_name="Lovelace", phone="5551234")

        self.assertEqual(str(patient), "Ada Lovelace")
        self.assertEqual(Patient.objects.count(), 1)


class PatientCreateViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staff",
            password="strong-password-123",
        )

    def test_create_patient_record(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patients:create"),
            {
                "first_name": "Grace",
                "last_name": "Hopper",
                "phone": "5559876",
                "email": "grace@example.com",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Patient.objects.count(), 1)
        patient = Patient.objects.get()
        self.assertEqual(patient.first_name, "Grace")
        self.assertEqual(patient.last_name, "Hopper")

    def test_patient_pages_require_login(self):
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
