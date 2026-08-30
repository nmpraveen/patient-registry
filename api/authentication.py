from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.settings import api_settings

from patients.auth_security import current_auth_version


User = get_user_model()


def token_auth_version(token):
    return int(token.get("auth_version", 1))


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


class AuthVersionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        try:
            validate_token_auth_version(validated_token, user)
        except InvalidToken as exc:
            raise AuthenticationFailed(str(exc), code="token_revoked") from exc
        return user
