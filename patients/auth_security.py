from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import AuthenticationThrottleBucket, UserSecurityState


AUTH_VERSION_SESSION_KEY = "medtrack_auth_version"
DEVICE_CREDENTIAL_SESSION_KEY = "medtrack_device_credential_id"


def current_auth_version(user):
    state, _ = UserSecurityState.objects.get_or_create(user=user)
    return state.auth_version


def bind_authenticated_session(request, user, *, device_credential=None):
    request.session[AUTH_VERSION_SESSION_KEY] = current_auth_version(user)
    if device_credential is None:
        request.session.pop(DEVICE_CREDENTIAL_SESSION_KEY, None)
    else:
        request.session[DEVICE_CREDENTIAL_SESSION_KEY] = device_credential.pk
    request.session.modified = True


def bump_auth_version(user, *, reason, actor=None, request=None):
    state, _ = UserSecurityState.objects.get_or_create(user=user)
    UserSecurityState.objects.filter(pk=state.pk).update(
        auth_version=F("auth_version") + 1,
        updated_at=timezone.now(),
    )
    state.refresh_from_db(fields=["auth_version", "updated_at"])
    from .audit import record_audit_event
    from .models import AuditEvent

    record_audit_event(
        category=AuditEvent.Category.IAM,
        action="auth.version_changed",
        actor=actor,
        request=request,
        object_type="user",
        object_id=user.pk,
        metadata={"reason": reason, "auth_version": state.auth_version},
    )
    return state.auth_version


def _client_ip(request):
    return (request.META.get("REMOTE_ADDR") or "unknown").strip().lower()


def _key_hash(scope, value):
    return salted_hmac(f"patients.auth_throttle.{scope}", value).hexdigest()


def _throttle_specs(request, identifier):
    normalized_identifier = (identifier or "").strip().casefold()
    ip = _client_ip(request)
    account_limit = getattr(settings, "AUTH_THROTTLE_ACCOUNT_LIMIT", 5)
    ip_limit = getattr(settings, "AUTH_THROTTLE_IP_LIMIT", 30)
    return [
        (_key_hash("account_ip", f"{ip}|{normalized_identifier}"), account_limit),
        (_key_hash("ip", ip), ip_limit),
    ]


def consume_auth_attempt(*, scope, request, identifier):
    now = timezone.now()
    window = timedelta(seconds=getattr(settings, "AUTH_THROTTLE_WINDOW_SECONDS", 900))
    block_for = timedelta(seconds=getattr(settings, "AUTH_THROTTLE_BLOCK_SECONDS", 900))
    retry_after = 0

    with transaction.atomic():
        for key_hash, limit in sorted(_throttle_specs(request, identifier)):
            bucket, _ = AuthenticationThrottleBucket.objects.select_for_update().get_or_create(
                scope=scope,
                key_hash=key_hash,
                defaults={"window_started_at": now},
            )
            if bucket.blocked_until and bucket.blocked_until > now:
                retry_after = max(retry_after, int((bucket.blocked_until - now).total_seconds()) + 1)
                continue
            if now - bucket.window_started_at >= window:
                bucket.failure_count = 0
                bucket.window_started_at = now
                bucket.blocked_until = None
            bucket.failure_count += 1
            if bucket.failure_count >= limit:
                bucket.blocked_until = now + block_for
            bucket.save(
                update_fields=["failure_count", "window_started_at", "blocked_until", "updated_at"]
            )
    return retry_after


def clear_auth_attempts(*, scope, request, identifier):
    key_hashes = [key_hash for key_hash, _ in _throttle_specs(request, identifier)]
    AuthenticationThrottleBucket.objects.filter(scope=scope, key_hash__in=key_hashes).update(
        failure_count=0,
        window_started_at=timezone.now(),
        blocked_until=None,
    )
