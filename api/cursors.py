import hashlib
import json
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import MobileOpaqueCursor


CURSOR_TTL = timedelta(minutes=15)
MAX_ACTIVE_CURSORS_PER_KIND = 256


class CursorValidationError(ValueError):
    pass


def binding_digest(binding):
    canonical = json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def purge_expired_mobile_cursors(*, limit=500, as_of=None):
    bounded_limit = max(1, min(int(limit), 5000))
    expired_ids = list(
        MobileOpaqueCursor.objects.filter(expires_at__lte=as_of or timezone.now())
        .order_by("expires_at", "pk")
        .values_list("pk", flat=True)[:bounded_limit]
    )
    if not expired_ids:
        return 0
    return MobileOpaqueCursor.objects.filter(pk__in=expired_ids).delete()[0]


def encode_cursor(*, user, kind, binding, position, context=None, snapshot=None):
    state = {"position": position}
    if snapshot is not None:
        state["snapshot"] = snapshot
    with transaction.atomic():
        purge_expired_mobile_cursors()
        token = secrets.token_urlsafe(32)
        MobileOpaqueCursor.objects.create(
            token_hash=_token_hash(token),
            user=user,
            kind=kind,
            binding_hash=binding_digest(binding),
            context_hash=binding_digest(context or {}),
            state=state,
            expires_at=timezone.now() + CURSOR_TTL,
        )
        retained_ids = list(
            MobileOpaqueCursor.objects.filter(user=user, kind=kind)
            .order_by("-created_at", "-pk")
            .values_list("pk", flat=True)[:MAX_ACTIVE_CURSORS_PER_KIND]
        )
        if retained_ids:
            MobileOpaqueCursor.objects.filter(user=user, kind=kind).exclude(pk__in=retained_ids).delete()
    return token


def decode_cursor(token, *, user, kind, binding, context=None):
    if not isinstance(token, str) or len(token) < 32 or len(token) > 128:
        raise CursorValidationError("Invalid cursor.")
    cursor = MobileOpaqueCursor.objects.filter(
        token_hash=_token_hash(token),
        user=user,
        kind=kind,
    ).first()
    if cursor is None or cursor.expires_at <= timezone.now():
        if cursor is not None:
            cursor.delete()
        raise CursorValidationError("Invalid or expired cursor.")
    if cursor.binding_hash != binding_digest(binding):
        raise CursorValidationError("Cursor does not match this request.")
    if cursor.context_hash != binding_digest(context or {}):
        raise CursorValidationError("Cursor is no longer valid for this authorization context.")
    payload = cursor.state
    if not isinstance(payload, dict) or not isinstance(payload.get("position"), dict):
        raise CursorValidationError("Invalid cursor position.")
    return payload
