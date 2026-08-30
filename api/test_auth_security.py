from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from patients.models import AuditEvent, CaseDataScope, RoleSetting


User = get_user_model()


class JwtAuthenticationSecurityTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="jwt-security-user",
            password="strong-password-123",
        )

    def obtain_tokens(self, password="strong-password-123"):
        return self.client.post(
            reverse("api:token_obtain_pair"),
            {"username": self.user.username, "password": password},
            format="json",
        )

    def test_password_change_immediately_invalidates_access_and_refresh_tokens(self):
        tokens = self.obtain_tokens()
        self.assertEqual(tokens.status_code, 200)
        access = tokens.json()["access"]
        refresh = tokens.json()["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get(reverse("api:me")).status_code, 200)

        self.user.set_password("new-strong-password-456")
        self.user.save(update_fields=["password"])

        self.assertEqual(self.client.get(reverse("api:me")).status_code, 401)
        self.client.credentials()
        rejected_refresh = self.client.post(
            reverse("api:token_refresh"),
            {"refresh": refresh},
            format="json",
        )
        self.assertEqual(rejected_refresh.status_code, 401)

        replacement = self.obtain_tokens(password="new-strong-password-456")
        self.assertEqual(replacement.status_code, 200)

    def test_role_policy_change_invalidates_tokens_for_role_members(self):
        role = RoleSetting.objects.create(
            role_name="JWT Scoped Role",
            case_data_scope=CaseDataScope.ASSIGNED,
        )
        group = Group.objects.create(name=role.role_name)
        self.user.groups.add(group)
        tokens = self.obtain_tokens()
        self.assertEqual(tokens.status_code, 200)

        role.case_data_scope = CaseDataScope.ALL
        role.save(update_fields=["case_data_scope"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens.json()['access']}")
        self.assertEqual(self.client.get(reverse("api:me")).status_code, 401)

    @override_settings(AUTH_THROTTLE_ACCOUNT_LIMIT=2, AUTH_THROTTLE_IP_LIMIT=20)
    def test_jwt_login_is_throttled_and_audited(self):
        url = reverse("api:token_obtain_pair")
        payload = {"username": self.user.username, "password": "wrong"}

        self.assertEqual(self.client.post(url, payload, format="json").status_code, 401)
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 401)
        blocked = self.client.post(
            url,
            {"username": self.user.username, "password": "strong-password-123"},
            format="json",
        )

        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked)
        self.assertTrue(
            AuditEvent.objects.filter(action="authentication.jwt.throttled", outcome=AuditEvent.Outcome.DENIED).exists()
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                action="authentication.jwt.failed",
                outcome=AuditEvent.Outcome.DENIED,
            ).count(),
            2,
        )

    def test_me_exposes_explicit_data_scope(self):
        role = RoleSetting.objects.create(
            role_name="JWT Intake Role",
            case_data_scope=CaseDataScope.ASSIGNED,
            can_access_call_queue=True,
            can_intake_patient_lookup=True,
        )
        group = Group.objects.create(name=role.role_name)
        self.user.groups.add(group)
        tokens = self.obtain_tokens()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens.json()['access']}")

        response = self.client.get(reverse("api:me"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data_scope"],
            {
                "case_data_scope": CaseDataScope.ASSIGNED,
                "call_queue": True,
                "intake_patient_lookup": True,
            },
        )
