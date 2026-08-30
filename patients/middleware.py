from django.contrib.auth import logout as auth_logout
from django.http import JsonResponse
from django.shortcuts import redirect

from .audit import record_audit_event, reset_current_request, set_current_request
from .auth_security import (
    AUTH_VERSION_SESSION_KEY,
    DEVICE_CREDENTIAL_SESSION_KEY,
    current_auth_version,
)
from .models import AuditEvent, DeviceApprovalPolicy, StaffDeviceCredential, StaffDeviceCredentialStatus


class AuditAndSessionSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_current_request(request)
        try:
            denial = self._enforce_session_security(request)
            if denial is not None:
                return denial
            return self.get_response(request)
        finally:
            reset_current_request(token)

    @staticmethod
    def _device_policy_targets(user):
        policy = DeviceApprovalPolicy.objects.filter(pk=1, enabled=True).first()
        return bool(policy and policy.targets_user(user))

    def _enforce_session_security(self, request):
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return None

        current_version = current_auth_version(user)
        bound_version = request.session.get(AUTH_VERSION_SESSION_KEY)
        device_policy_targets_user = self._device_policy_targets(user)
        if bound_version is None and not device_policy_targets_user:
            request.session[AUTH_VERSION_SESSION_KEY] = current_version
            bound_version = current_version

        device_id = request.session.get(DEVICE_CREDENTIAL_SESSION_KEY)
        invalid_reason = ""
        if bound_version != current_version:
            invalid_reason = "auth_version_changed"
        elif device_policy_targets_user:
            approved = StaffDeviceCredential.objects.filter(
                pk=device_id,
                user=user,
                status=StaffDeviceCredentialStatus.APPROVED,
            ).exists()
            if not approved:
                invalid_reason = "device_not_approved"

        if not invalid_reason:
            return None

        record_audit_event(
            category=AuditEvent.Category.IAM,
            action="session.revoked",
            outcome=AuditEvent.Outcome.DENIED,
            actor=user,
            request=request,
            object_type="user",
            object_id=user.pk,
            metadata={"reason": invalid_reason},
        )
        auth_logout(request)
        if request.path.startswith("/api/"):
            return JsonResponse({"detail": "Authentication credentials are no longer valid."}, status=401)
        login_url = "/login/"
        if request.path and request.path != "/":
            login_url = f"{login_url}?next={request.get_full_path()}"
        return redirect(login_url)
