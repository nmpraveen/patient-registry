import hashlib
import json

from django.core import signing


CURSOR_SALT = "medtrack.mobile.keyset.v1"


class CursorValidationError(ValueError):
    pass


def binding_digest(binding):
    canonical = json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def encode_cursor(*, kind, binding, position, context=None, snapshot=None):
    payload = {
        "v": 1,
        "kind": kind,
        "binding": binding_digest(binding),
        "position": position,
    }
    if context:
        payload["context"] = context
    if snapshot:
        payload["snapshot"] = snapshot
    return signing.dumps(payload, salt=CURSOR_SALT, compress=True)


def decode_cursor(token, *, kind, binding, context=None):
    try:
        payload = signing.loads(token, salt=CURSOR_SALT)
    except (signing.BadSignature, TypeError, ValueError) as exc:
        raise CursorValidationError("Invalid cursor.") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise CursorValidationError("Invalid cursor.")
    if payload.get("kind") != kind or payload.get("binding") != binding_digest(binding):
        raise CursorValidationError("Cursor does not match this request.")
    if (payload.get("context") or {}) != (context or {}):
        raise CursorValidationError("Cursor is no longer valid for this authorization context.")
    if not isinstance(payload.get("position"), dict):
        raise CursorValidationError("Invalid cursor position.")
    return payload
