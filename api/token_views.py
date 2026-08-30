import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework import status
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken, TokenError, UntypedToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from patients.audit import record_audit_event
from patients.auth_security import (
    bump_auth_version,
    clear_auth_attempts,
    consume_auth_attempt,
    current_auth_version,
    user_requires_device_approval,
)
from patients.models import (
    AuditEvent,
    StaffDeviceCredentialStatus,
    StaffMobileDeviceCredential,
)

from .authentication import token_user, validate_token_security_context


User = get_user_model()


class AuthVersionTokenObtainPairSerializer(TokenObtainPairSerializer):
    MAX_PENDING_MOBILE_DEVICES = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["device_id"] = serializers.UUIDField(required=False, write_only=True)
        self.fields["device_secret"] = serializers.CharField(
            required=False,
            write_only=True,
            trim_whitespace=False,
            max_length=128,
        )
        self.fields["device_label"] = serializers.CharField(
            required=False,
            write_only=True,
            allow_blank=True,
            max_length=120,
        )

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["auth_version"] = current_auth_version(user)
        return token

    def _pending_registration(self, attrs):
        with transaction.atomic():
            # The user row is stable for the lifetime of every credential and
            # serializes the count/create boundary across all app workers.
            User.objects.select_for_update().only("pk").get(pk=self.user.pk)
            pending_count = StaffMobileDeviceCredential.objects.filter(
                user=self.user,
                status=StaffDeviceCredentialStatus.PENDING,
            ).count()
            if pending_count >= self.MAX_PENDING_MOBILE_DEVICES:
                raise PermissionDenied(
                    "Mobile device approval is required; the pending-device limit has been reached."
                )
            raw_secret = secrets.token_urlsafe(32)
            credential = StaffMobileDeviceCredential(
                user=self.user,
                device_label=(attrs.get("device_label") or "Mobile device").strip(),
            )
            credential.set_secret(raw_secret)
            credential.save()
        return {
            "device_approval_required": True,
            "status": StaffDeviceCredentialStatus.PENDING,
            "device_id": str(credential.device_id),
            "device_secret": raw_secret,
        }

    def _validated_mobile_credential(self, attrs):
        device_id = attrs.get("device_id")
        device_secret = attrs.get("device_secret")
        if bool(device_id) != bool(device_secret):
            raise serializers.ValidationError(
                "device_id and device_secret must be supplied together."
            )
        if device_id is None:
            return None
        credential = StaffMobileDeviceCredential.objects.filter(device_id=device_id).first()
        if credential is None or credential.user_id != self.user.pk or not credential.check_secret(device_secret):
            raise AuthenticationFailed("Mobile device credential is not valid.")
        if credential.status == StaffDeviceCredentialStatus.PENDING:
            return {
                "device_approval_required": True,
                "status": credential.status,
                "device_id": str(credential.device_id),
            }
        if credential.status != StaffDeviceCredentialStatus.APPROVED:
            raise PermissionDenied("Mobile device credential is not approved.")
        return credential

    def validate(self, attrs):
        TokenObtainSerializer.validate(self, attrs)
        credential = None
        if user_requires_device_approval(self.user):
            credential = self._validated_mobile_credential(attrs)
            if credential is None:
                return self._pending_registration(attrs)
            if isinstance(credential, dict):
                return credential

        refresh = self.get_token(self.user)
        if credential is not None:
            refresh["mobile_device_id"] = str(credential.device_id)
            StaffMobileDeviceCredential.objects.filter(pk=credential.pk).update(last_used_at=timezone.now())
        OutstandingToken.objects.filter(
            user=self.user,
            jti=refresh[api_settings.JTI_CLAIM],
        ).update(token=str(refresh))
        return {"refresh": str(refresh), "access": str(refresh.access_token)}


class AuthVersionTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            untyped = UntypedToken(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        if untyped.get(api_settings.TOKEN_TYPE_CLAIM) != "refresh":
            raise InvalidToken("Token is not a refresh token.")
        user = token_user(untyped)
        validate_token_security_context(untyped, user)
        self.user = user
        jti = untyped.get(api_settings.JTI_CLAIM)
        if not jti:
            raise InvalidToken("Refresh token has no identifier.")

        replay_detected = False
        data = None
        with transaction.atomic():
            outstanding = (
                OutstandingToken.objects.select_for_update()
                .filter(user=user, jti=jti)
                .first()
            )
            if outstanding is None or outstanding.token != attrs["refresh"]:
                raise InvalidToken("Refresh token is not an issued token.")
            if BlacklistedToken.objects.filter(token=outstanding).exists():
                replay_detected = True
                for family_token in OutstandingToken.objects.select_for_update().filter(user=user):
                    BlacklistedToken.objects.get_or_create(token=family_token)
                bump_auth_version(
                    user,
                    reason="refresh_token_reuse_detected",
                    request=self.context.get("request"),
                )
                record_audit_event(
                    category=AuditEvent.Category.IAM,
                    action="authentication.jwt_refresh.reuse_detected",
                    outcome=AuditEvent.Outcome.DENIED,
                    actor=user,
                    request=self.context.get("request"),
                    object_type="user",
                    object_id=user.pk,
                    metadata={"refresh_jti_hash": salted_hmac("api.refresh_replay", jti).hexdigest()},
                )
            else:
                data = super().validate(attrs)

        if replay_detected:
            raise InvalidToken("Refresh token reuse was detected; the token family was revoked.")
        return data


class AuthThrottleViewMixin:
    throttle_scope = "jwt"

    def throttle_identifier(self, request):
        return request.data.get("username") or request.data.get("refresh") or ""

    def post(self, request, *args, **kwargs):
        identifier = self.throttle_identifier(request)
        retry_after = consume_auth_attempt(
            scope=self.throttle_scope,
            request=request,
            identifier=identifier,
        )
        if retry_after:
            record_audit_event(
                category=AuditEvent.Category.IAM,
                action=f"authentication.{self.throttle_scope}.throttled",
                outcome=AuditEvent.Outcome.DENIED,
                request=request,
            )
            response = Response(
                {"detail": "Too many authentication attempts. Try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response["Retry-After"] = str(retry_after)
            return response

        try:
            response = super().post(request, *args, **kwargs)
        except APIException:
            record_audit_event(
                category=AuditEvent.Category.IAM,
                action=f"authentication.{self.throttle_scope}.failed",
                outcome=AuditEvent.Outcome.DENIED,
                request=request,
            )
            raise
        authentication_succeeded = response.status_code == status.HTTP_200_OK
        if response.status_code == status.HTTP_200_OK and response.data.get("device_approval_required"):
            response.status_code = status.HTTP_202_ACCEPTED
            authentication_succeeded = True
        if authentication_succeeded:
            clear_auth_attempts(scope=self.throttle_scope, request=request, identifier=identifier)
            actor = None
            if self.throttle_scope == "jwt":
                actor = User.objects.filter(username=request.data.get("username", "")).first()
            else:
                try:
                    actor = token_user(RefreshToken(request.data.get("refresh", "")))
                except (InvalidToken, TokenError):
                    actor = None
            record_audit_event(
                category=AuditEvent.Category.IAM,
                action=f"authentication.{self.throttle_scope}.succeeded",
                actor=actor,
                request=request,
                object_type="user" if actor else "",
                object_id=actor.pk if actor else "",
            )
        else:
            record_audit_event(
                category=AuditEvent.Category.IAM,
                action=f"authentication.{self.throttle_scope}.failed",
                outcome=AuditEvent.Outcome.DENIED,
                request=request,
            )
        return response


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class AuthVersionTokenObtainPairView(AuthThrottleViewMixin, TokenObtainPairView):
    serializer_class = AuthVersionTokenObtainPairSerializer
    throttle_scope = "jwt"


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class AuthVersionTokenRefreshView(AuthThrottleViewMixin, TokenRefreshView):
    serializer_class = AuthVersionTokenRefreshSerializer
    throttle_scope = "jwt_refresh"
