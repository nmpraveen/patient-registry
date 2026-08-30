from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, BrokenBarrierError
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import close_old_connections, connection
from django.db.models.query import QuerySet
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITransactionTestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from api.token_views import AuthVersionTokenObtainPairSerializer
from patients.auth_security import current_auth_version
from patients.models import (
    AuditEvent,
    AuthenticationThrottleBucket,
    CaseDataScope,
    DeviceApprovalPolicy,
    RoleSetting,
    StaffDeviceCredentialStatus,
    StaffMobileDeviceCredential,
)

from .models import MobileDeviceToken


User = get_user_model()


class JwtAuthenticationSecurityTests(APITransactionTestCase):
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
        device_token = MobileDeviceToken.objects.create(
            user=self.user,
            token="password-change-device-token",
        )

        self.user.set_password("new-strong-password-456")
        self.user.save(update_fields=["password"])

        device_token.refresh_from_db()
        self.assertFalse(device_token.is_active)
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

    def test_missing_malformed_and_nonpositive_auth_version_claims_fail_closed(self):
        for claim_value in (None, "1", 0, -1):
            token = AccessToken.for_user(self.user)
            if claim_value is not None:
                token["auth_version"] = claim_value
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            self.assertEqual(self.client.get(reverse("api:me")).status_code, 401)

        refresh = RefreshToken.for_user(self.user)
        rejected = self.client.post(
            reverse("api:token_refresh"),
            {"refresh": str(refresh)},
            format="json",
        )
        self.assertEqual(rejected.status_code, 401)

    def test_refresh_rotates_and_replay_revokes_the_entire_family(self):
        tokens = self.obtain_tokens().json()
        original_version = current_auth_version(self.user)
        rotated = self.client.post(
            reverse("api:token_refresh"),
            {"refresh": tokens["refresh"]},
            format="json",
        )
        self.assertEqual(rotated.status_code, 200)
        self.assertIn("refresh", rotated.json())
        self.assertEqual(
            RefreshToken(rotated.json()["refresh"])["auth_version"],
            original_version,
        )

        replay = self.client.post(
            reverse("api:token_refresh"),
            {"refresh": tokens["refresh"]},
            format="json",
        )
        self.assertEqual(replay.status_code, 401)
        self.assertGreater(current_auth_version(self.user), original_version)
        self.assertTrue(
            AuditEvent.objects.filter(action="authentication.jwt_refresh.reuse_detected").exists()
        )
        self.assertNotIn(tokens["refresh"], str(AuditEvent.objects.last().metadata))

        family_rejected = self.client.post(
            reverse("api:token_refresh"),
            {"refresh": rotated.json()["refresh"]},
            format="json",
        )
        self.assertEqual(family_rejected.status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {rotated.json()['access']}")
        self.assertEqual(self.client.get(reverse("api:me")).status_code, 401)

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

    def test_role_policy_create_delete_and_recreate_revoke_existing_members(self):
        group = Group.objects.create(name="Late Policy Role")
        self.user.groups.add(group)
        initial_version = current_auth_version(self.user)

        role = RoleSetting.objects.create(
            role_name=group.name,
            case_data_scope=CaseDataScope.ALL,
        )
        created_version = current_auth_version(self.user)
        self.assertGreater(created_version, initial_version)

        role.delete()
        deleted_version = current_auth_version(self.user)
        self.assertGreater(deleted_version, created_version)

        RoleSetting.objects.create(
            role_name=group.name,
            case_data_scope=CaseDataScope.ALL,
        )
        self.assertGreater(current_auth_version(self.user), deleted_version)

    def test_role_group_rename_and_delete_revoke_existing_members(self):
        role = RoleSetting.objects.create(
            role_name="Mutable Role Group",
            case_data_scope=CaseDataScope.ASSIGNED,
        )
        group = Group.objects.create(name=role.role_name)
        self.user.groups.add(group)
        initial_version = current_auth_version(self.user)

        group.name = "Renamed Role Group"
        group.save(update_fields=["name"])
        renamed_version = current_auth_version(self.user)
        self.assertGreater(renamed_version, initial_version)

        group.delete()
        self.assertGreater(current_auth_version(self.user), renamed_version)

    def test_targeted_mobile_login_requires_server_issued_approved_credential(self):
        policy = DeviceApprovalPolicy.get_solo()
        policy.enabled = True
        policy.save()
        policy.target_users.add(self.user)

        pending = self.obtain_tokens()
        self.assertEqual(pending.status_code, 202)
        self.assertNotIn("access", pending.json())
        device_id = pending.json()["device_id"]
        device_secret = pending.json()["device_secret"]
        credential = StaffMobileDeviceCredential.objects.get(device_id=device_id)
        self.assertTrue(credential.check_secret(device_secret))
        self.assertNotEqual(credential.secret_hash, device_secret)

        credential.status = StaffDeviceCredentialStatus.APPROVED
        credential.approved_at = timezone.now()
        credential.save(update_fields=["status", "approved_at"])
        approved = self.client.post(
            reverse("api:token_obtain_pair"),
            {
                "username": self.user.username,
                "password": "strong-password-123",
                "device_id": device_id,
                "device_secret": device_secret,
            },
            format="json",
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(
            str(RefreshToken(approved.json()["refresh"])["mobile_device_id"]),
            device_id,
        )

        credential.status = StaffDeviceCredentialStatus.REVOKED
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["status", "revoked_at"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {approved.json()['access']}")
        self.assertEqual(self.client.get(reverse("api:me")).status_code, 401)
        self.client.credentials()
        self.assertEqual(
            self.client.post(
                reverse("api:token_refresh"),
                {"refresh": approved.json()["refresh"]},
                format="json",
            ).status_code,
            401,
        )

    @skipUnless(connection.vendor == "postgresql", "Row-lock concurrency requires PostgreSQL.")
    def test_pending_mobile_registration_cap_is_atomic_under_concurrency(self):
        worker_count = 8
        start_barrier = Barrier(worker_count)
        count_barrier = Barrier(worker_count)
        real_count = QuerySet.count

        def synchronized_count(queryset):
            result = real_count(queryset)
            if queryset.model is StaffMobileDeviceCredential:
                try:
                    count_barrier.wait(timeout=1)
                except BrokenBarrierError:
                    pass
            return result

        def register(index):
            close_old_connections()
            try:
                serializer = AuthVersionTokenObtainPairSerializer()
                serializer.user = User.objects.get(pk=self.user.pk)
                start_barrier.wait()
                try:
                    serializer._pending_registration(
                        {"device_label": f"Concurrent device {index}"}
                    )
                    return "pending"
                except PermissionDenied:
                    return "limited"
            finally:
                close_old_connections()

        with patch.object(QuerySet, "count", new=synchronized_count):
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                results = list(executor.map(register, range(worker_count)))

        self.assertEqual(results.count("pending"), 3)
        self.assertEqual(results.count("limited"), worker_count - 3)
        self.assertEqual(
            StaffMobileDeviceCredential.objects.filter(
                user=self.user,
                status=StaffDeviceCredentialStatus.PENDING,
            ).count(),
            3,
        )

    def test_targeted_refresh_rejects_legacy_pending_and_revoked_mobile_credentials(self):
        policy = DeviceApprovalPolicy.get_solo()
        policy.enabled = True
        policy.save()
        policy.target_users.add(self.user)

        legacy = RefreshToken.for_user(self.user)
        legacy["auth_version"] = current_auth_version(self.user)

        pending = StaffMobileDeviceCredential(user=self.user, device_label="Pending")
        pending.set_secret("pending-secret")
        pending.save()
        pending_token = RefreshToken.for_user(self.user)
        pending_token["auth_version"] = current_auth_version(self.user)
        pending_token["mobile_device_id"] = str(pending.device_id)

        revoked = StaffMobileDeviceCredential(
            user=self.user,
            device_label="Revoked",
            status=StaffDeviceCredentialStatus.REVOKED,
            revoked_at=timezone.now(),
        )
        revoked.set_secret("revoked-secret")
        revoked.save()
        revoked_token = RefreshToken.for_user(self.user)
        revoked_token["auth_version"] = current_auth_version(self.user)
        revoked_token["mobile_device_id"] = str(revoked.device_id)

        for token in (legacy, pending_token, revoked_token):
            response = self.client.post(
                reverse("api:token_refresh"),
                {"refresh": str(token)},
                format="json",
            )
            self.assertEqual(response.status_code, 401)

    def test_device_policy_group_target_is_enforced_for_jwt(self):
        group = Group.objects.create(name="Mobile Approval Group")
        self.user.groups.add(group)
        policy = DeviceApprovalPolicy.get_solo()
        policy.enabled = True
        policy.save()
        policy.target_groups.add(group)

        response = self.obtain_tokens()

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["device_approval_required"])

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

    @override_settings(AUTH_THROTTLE_ACCOUNT_LIMIT=20, AUTH_THROTTLE_IP_LIMIT=3)
    def test_successful_account_does_not_reset_other_failures_for_the_ip(self):
        other = User.objects.create_user(username="valid-reset-user", password="valid-password-123")
        url = reverse("api:token_obtain_pair")
        self.assertEqual(
            self.client.post(url, {"username": self.user.username, "password": "wrong"}, format="json").status_code,
            401,
        )
        self.assertEqual(
            self.client.post(url, {"username": other.username, "password": "valid-password-123"}, format="json").status_code,
            200,
        )
        self.assertEqual(
            self.client.post(url, {"username": self.user.username, "password": "wrong"}, format="json").status_code,
            401,
        )
        self.assertEqual(
            self.client.post(url, {"username": self.user.username, "password": "wrong"}, format="json").status_code,
            401,
        )
        blocked = self.client.post(
            url,
            {"username": other.username, "password": "valid-password-123"},
            format="json",
        )
        self.assertEqual(blocked.status_code, 429)

    @override_settings(AUTH_THROTTLE_ACCOUNT_LIMIT=20, AUTH_THROTTLE_IP_LIMIT=1)
    def test_blocked_ip_does_not_create_random_identifier_buckets(self):
        url = reverse("api:token_obtain_pair")
        self.client.post(url, {"username": "first-random", "password": "wrong"}, format="json")
        initial_count = AuthenticationThrottleBucket.objects.count()
        for index in range(20):
            response = self.client.post(
                url,
                {"username": f"random-{index}", "password": "wrong"},
                format="json",
            )
            self.assertEqual(response.status_code, 429)
        self.assertEqual(AuthenticationThrottleBucket.objects.count(), initial_count)

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
