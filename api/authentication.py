from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.settings import api_settings

from patients.auth_security import current_auth_version, parse_positive_auth_version, user_requires_device_approval
from patients.models import StaffDeviceCredentialStatus, StaffMobileDeviceCredential


User = get_user_model()


def token_auth_version(token):
    try:
        return parse_positive_auth_version(token.get("auth_version"))
    except ValueError as exc:
        raise InvalidToken("Token has no valid authentication version.") from exc


def token_user(token):
    user_id = token.get(api_settings.USER_ID_CLAIM)
    if user_id is None:
        raise InvalidToken("Token has no user identifier.")
    try:
        user = User.objects.get(**{api_settings.USER_ID_FIELD: user_id})
    except User.DoesNotExist as exc:
        raise InvalidToken("Token user no longer exists.") from exc
    if not user.is_active:
        raise InvalidToken("Token user is inactive.")
    return user


def validate_token_auth_version(token, user):
    if token_auth_version(token) != current_auth_version(user):
        raise InvalidToken("Token was revoked by a security change.")


def validate_token_security_context(token, user):
    validate_token_auth_version(token, user)
    if not user_requires_device_approval(user):
        return
    device_id = token.get("mobile_device_id")
    if not device_id:
        raise InvalidToken("Token has no approved mobile device credential.")
    try:
        approved = StaffMobileDeviceCredential.objects.filter(
            device_id=device_id,
            user=user,
            status=StaffDeviceCredentialStatus.APPROVED,
        ).exists()
    except (TypeError, ValueError, ValidationError) as exc:
        raise InvalidToken("Token has no valid mobile device credential.") from exc
    if not approved:
        raise InvalidToken("Token mobile device credential is not approved.")


class AuthVersionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        try:
            validate_token_security_context(validated_token, user)
        except InvalidToken as exc:
            raise AuthenticationFailed(str(exc), code="token_revoked") from exc
        return user
