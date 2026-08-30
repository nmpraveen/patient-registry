from datetime import timedelta
import ipaddress

from django.apps import apps as django_apps
from django.conf import settings
from django.db import connection, models, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import AuthenticationThrottleBucket, UserSecurityState


AUTH_VERSION_SESSION_KEY = "medtrack_auth_version"
DEVICE_CREDENTIAL_SESSION_KEY = "medtrack_device_credential_id"
AUTH_IDENTIFIER_MAX_LENGTH = 256


def parse_positive_auth_version(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Authentication version must be a positive integer.")
    return value


def current_auth_version(user):
    state, _ = UserSecurityState.objects.get_or_create(user=user)
    return parse_positive_auth_version(state.auth_version)


def user_requires_device_approval(user):
    from .models import DeviceApprovalPolicy

    policy = DeviceApprovalPolicy.objects.filter(pk=1, enabled=True).first()
    return bool(policy and policy.targets_user(user))


def bind_authenticated_session(request, user, *, device_credential=None):
    request.session[AUTH_VERSION_SESSION_KEY] = current_auth_version(user)
    if device_credential is None:
        request.session.pop(DEVICE_CREDENTIAL_SESSION_KEY, None)
    else:
        request.session[DEVICE_CREDENTIAL_SESSION_KEY] = device_credential.pk
    request.session.modified = True


def bump_auth_version(user, *, reason, actor=None, request=None):
    with transaction.atomic():
        state, _ = UserSecurityState.objects.get_or_create(user=user)
        state = UserSecurityState.objects.select_for_update().get(pk=state.pk)
        UserSecurityState.objects.filter(pk=state.pk).update(
            auth_version=F("auth_version") + 1,
            updated_at=timezone.now(),
        )
        state.refresh_from_db(fields=["auth_version", "updated_at"])

        deactivated_mobile_tokens = 0
        MobileDeviceToken = django_apps.get_model("api", "MobileDeviceToken")
        database_tables = set(connection.introspection.table_names())
        if MobileDeviceToken._meta.db_table in database_tables:
            deactivated_mobile_tokens = MobileDeviceToken.objects.filter(
                user_id=user.pk,
                is_active=True,
            ).update(is_active=False, updated_at=timezone.now())

        MobileNotificationState = django_apps.get_model("api", "MobileNotificationState")
        if MobileNotificationState._meta.db_table in database_tables:
            from api.notifications import bump_notification_epochs

            bump_notification_epochs([user.pk])

        from .audit import record_audit_event
        from .models import AuditEvent

        record_audit_event(
            category=AuditEvent.Category.IAM,
            action="auth.version_changed",
            actor=actor,
            request=request,
            object_type="user",
            object_id=user.pk,
            metadata={
                "reason": reason,
                "auth_version": state.auth_version,
                "deactivated_mobile_token_count": deactivated_mobile_tokens,
            },
        )
        return state.auth_version


def _client_ip(request):
    remote_value = (request.META.get("REMOTE_ADDR") or "").strip()
    try:
        remote_ip = ipaddress.ip_address(remote_value)
    except ValueError:
        return "unknown"

    trusted_networks = []
    for raw_network in getattr(settings, "AUTH_TRUSTED_PROXY_CIDRS", []):
        try:
            trusted_networks.append(ipaddress.ip_network(str(raw_network).strip(), strict=False))
        except ValueError:
            continue
    if not any(remote_ip in network for network in trusted_networks):
        return remote_ip.compressed

    header_name = getattr(settings, "AUTH_CLIENT_IP_HEADER", "HTTP_X_FORWARDED_FOR")
    if header_name not in {"HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP"}:
        return remote_ip.compressed
    forwarded_value = (request.META.get(header_name) or "").strip()
    if not forwarded_value:
        return remote_ip.compressed
    raw_chain = (
        [part.strip() for part in forwarded_value.split(",")]
        if header_name == "HTTP_X_FORWARDED_FOR"
        else [forwarded_value]
    )
    if not raw_chain or len(raw_chain) > 32:
        return remote_ip.compressed
    try:
        forwarded_chain = [ipaddress.ip_address(part) for part in raw_chain]
    except ValueError:
        return remote_ip.compressed
    for candidate in reversed(forwarded_chain):
        if not any(candidate in network for network in trusted_networks):
            return candidate.compressed
    return remote_ip.compressed


def _key_hash(scope, value):
    return salted_hmac(f"patients.auth_throttle.{scope}", value).hexdigest()


def _normalized_identifier(identifier):
    max_length = max(
        32,
        min(getattr(settings, "AUTH_THROTTLE_IDENTIFIER_MAX_LENGTH", AUTH_IDENTIFIER_MAX_LENGTH), 1024),
    )
    return str(identifier or "").strip().casefold()[:max_length]


def _bucket_scope(scope, kind):
    normalized_scope = "".join(character for character in str(scope or "") if character.isalnum() or character == "_")
    return f"{normalized_scope[:12]}:{kind}"


def _throttle_keys(request, identifier):
    ip = _client_ip(request)
    normalized_identifier = _normalized_identifier(identifier)
    return {
        "ip": _key_hash("ip", ip),
        "account": _key_hash("account_ip", f"{ip}|{normalized_identifier}"),
    }


def cleanup_expired_auth_buckets(*, now=None):
    now = now or timezone.now()
    minimum_retention = (
        getattr(settings, "AUTH_THROTTLE_WINDOW_SECONDS", 900)
        + getattr(settings, "AUTH_THROTTLE_BLOCK_SECONDS", 900)
    )
    retention_seconds = max(
        minimum_retention,
        getattr(settings, "AUTH_THROTTLE_RETENTION_SECONDS", 86400),
    )
    batch_size = max(1, min(getattr(settings, "AUTH_THROTTLE_CLEANUP_BATCH_SIZE", 1000), 5000))
    stale_ids = list(
        AuthenticationThrottleBucket.objects.filter(
            updated_at__lt=now - timedelta(seconds=retention_seconds),
        )
        .filter(models.Q(blocked_until__isnull=True) | models.Q(blocked_until__lte=now))
        .order_by("updated_at")
        .values_list("pk", flat=True)[:batch_size]
    )
    if stale_ids:
        AuthenticationThrottleBucket.objects.filter(pk__in=stale_ids).delete()
    return len(stale_ids)


def _locked_bucket(*, scope, key_hash, now):
    return AuthenticationThrottleBucket.objects.select_for_update().get_or_create(
        scope=scope,
        key_hash=key_hash,
        defaults={"window_started_at": now},
    )[0]


def _reset_expired_window(bucket, *, now, window):
    if now - bucket.window_started_at >= window:
        bucket.failure_count = 0
        bucket.window_started_at = now
        bucket.blocked_until = None


def _retry_after(bucket, *, now):
    if bucket.blocked_until and bucket.blocked_until > now:
        return int((bucket.blocked_until - now).total_seconds()) + 1
    return 0


def consume_auth_attempt(*, scope, request, identifier):
    now = timezone.now()
    window = timedelta(seconds=getattr(settings, "AUTH_THROTTLE_WINDOW_SECONDS", 900))
    block_for = timedelta(seconds=getattr(settings, "AUTH_THROTTLE_BLOCK_SECONDS", 900))
    account_limit = max(1, getattr(settings, "AUTH_THROTTLE_ACCOUNT_LIMIT", 5))
    ip_limit = max(1, getattr(settings, "AUTH_THROTTLE_IP_LIMIT", 30))
    keys = _throttle_keys(request, identifier)
    cleanup_expired_auth_buckets(now=now)

    with transaction.atomic():
        ip_bucket = _locked_bucket(
            scope=_bucket_scope(scope, "ip"),
            key_hash=keys["ip"],
            now=now,
        )
        _reset_expired_window(ip_bucket, now=now, window=window)
        retry_after = _retry_after(ip_bucket, now=now)
        if retry_after:
            return retry_after

        ip_bucket.failure_count += 1
        if ip_bucket.failure_count >= ip_limit:
            ip_bucket.blocked_until = now + block_for
        ip_bucket.save(update_fields=["failure_count", "window_started_at", "blocked_until", "updated_at"])

        account_bucket = _locked_bucket(
            scope=_bucket_scope(scope, "account"),
            key_hash=keys["account"],
            now=now,
        )
        _reset_expired_window(account_bucket, now=now, window=window)
        retry_after = _retry_after(account_bucket, now=now)
        if retry_after:
            return retry_after
        account_bucket.failure_count += 1
        if account_bucket.failure_count >= account_limit:
            account_bucket.blocked_until = now + block_for
        account_bucket.save(update_fields=["failure_count", "window_started_at", "blocked_until", "updated_at"])
    return 0


def clear_auth_attempts(*, scope, request, identifier):
    now = timezone.now()
    keys = _throttle_keys(request, identifier)
    ip_limit = max(1, getattr(settings, "AUTH_THROTTLE_IP_LIMIT", 30))
    with transaction.atomic():
        account_bucket = AuthenticationThrottleBucket.objects.select_for_update().filter(
            scope=_bucket_scope(scope, "account"),
            key_hash=keys["account"],
        ).first()
        if account_bucket is not None:
            account_bucket.failure_count = 0
            account_bucket.window_started_at = now
            account_bucket.blocked_until = None
            account_bucket.save(
                update_fields=["failure_count", "window_started_at", "blocked_until", "updated_at"]
            )

        # consume_auth_attempt reserves one coarse-IP attempt before credentials
        # are checked. Release only this successful reservation; retain every
        # earlier IP failure and its original window start.
        ip_bucket = AuthenticationThrottleBucket.objects.select_for_update().filter(
            scope=_bucket_scope(scope, "ip"),
            key_hash=keys["ip"],
        ).first()
        if ip_bucket is not None and ip_bucket.failure_count:
            ip_bucket.failure_count -= 1
            if ip_bucket.failure_count < ip_limit:
                ip_bucket.blocked_until = None
            ip_bucket.save(update_fields=["failure_count", "blocked_until", "updated_at"])
