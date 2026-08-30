from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from patients.audit import record_audit_event
from patients.auth_security import clear_auth_attempts, consume_auth_attempt, current_auth_version
from patients.models import AuditEvent

from .authentication import token_user, validate_token_auth_version


User = get_user_model()


class AuthVersionTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["auth_version"] = current_auth_version(user)
        return token


class AuthVersionTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            refresh = self.token_class(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        user = token_user(refresh)
        validate_token_auth_version(refresh, user)
        self.user = user
        return super().validate(attrs)


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
        if response.status_code == status.HTTP_200_OK:
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


class AuthVersionTokenObtainPairView(AuthThrottleViewMixin, TokenObtainPairView):
    serializer_class = AuthVersionTokenObtainPairSerializer
    throttle_scope = "jwt"


class AuthVersionTokenRefreshView(AuthThrottleViewMixin, TokenRefreshView):
    serializer_class = AuthVersionTokenRefreshSerializer
    throttle_scope = "jwt_refresh"
