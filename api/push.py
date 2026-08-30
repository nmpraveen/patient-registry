from pathlib import Path

from django.conf import settings


PERMANENT_FCM_ERROR_NAMES = {
    "InvalidArgumentError",
    "SenderIdMismatchError",
    "UnregisteredError",
}
PERMANENT_FCM_ERROR_MARKERS = {
    "invalid-registration-token",
    "registration-token-not-registered",
    "sender-id-mismatch",
    "unregistered",
}
FCM_CHANNEL_IDS = {
    "assignment": "assignments",
    "assignments": "assignments",
    "red_flag": "red_flags",
    "red_flags": "red_flags",
    "overdue": "overdue",
}
FCM_HIGH_PRIORITY_CHANNELS = {"assignments", "red_flags"}
FCM_GENERIC_COPY = {
    "assignment": ("MEDTRACK assignment", "Open MEDTRACK to review an assignment update."),
    "red_flag": ("MEDTRACK priority update", "Open MEDTRACK to review a priority update."),
    "overdue": ("MEDTRACK task update", "Open MEDTRACK to review a task update."),
}


def firebase_configured():
    return bool(getattr(settings, "FCM_ENABLED", False) and _credentials_file())


def send_mobile_notification(notification):
    from .notifications import notification_is_authorized

    if not notification_is_authorized(notification):
        if notification.pk:
            notification.delete()
        return {"sent": False, "reason": "authorization_revoked"}

    tokens = list(
        notification.user.mobile_device_tokens.filter(is_active=True).values_list("token", flat=True)
    )
    if not tokens:
        return {"sent": False, "reason": "no_active_tokens"}

    credentials_file = _credentials_file()
    if not getattr(settings, "FCM_ENABLED", False) or not credentials_file:
        return {"sent": False, "reason": "fcm_not_configured"}

    try:
        response = _deliver_fcm(notification, tokens, credentials_file)
    except Exception as exc:  # Firebase config must never break normal API writes.
        return {
            "sent": False,
            "reason": "fcm_delivery_failed",
            "error_category": _fcm_error_category(exc),
        }

    inactive_count = _deactivate_permanently_failed_tokens(tokens, response.responses)
    return {
        "sent": True,
        "success_count": response.success_count,
        "failure_count": response.failure_count,
        "inactive_token_count": inactive_count,
    }


def _deactivate_permanently_failed_tokens(tokens, responses):
    permanent_failures = _permanent_failure_tokens(tokens, responses)
    if not permanent_failures:
        return 0

    from .models import MobileDeviceToken

    return MobileDeviceToken.objects.filter(token__in=permanent_failures, is_active=True).update(is_active=False)


def _permanent_failure_tokens(tokens, responses):
    failed_tokens = []
    for token, item_response in zip(tokens, responses):
        exception = getattr(item_response, "exception", None)
        if exception and _is_permanent_fcm_error(exception):
            failed_tokens.append(token)
    return failed_tokens


def _is_permanent_fcm_error(exception):
    if exception.__class__.__name__ in PERMANENT_FCM_ERROR_NAMES:
        return True
    code = str(getattr(exception, "code", "") or "").lower()
    message = str(exception).lower()
    return any(marker in code or marker in message for marker in PERMANENT_FCM_ERROR_MARKERS)


def _build_multicast_message(messaging, notification, tokens):
    channel_id = _channel_id_for_notification(notification)
    title, body = FCM_GENERIC_COPY.get(
        notification.notification_type,
        ("MEDTRACK update", "Open MEDTRACK to review an update."),
    )
    return messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data=_message_data(notification),
        android=messaging.AndroidConfig(
            priority="high" if channel_id in FCM_HIGH_PRIORITY_CHANNELS else "normal",
            notification=messaging.AndroidNotification(channel_id=channel_id),
        ),
    )


def _message_data(notification):
    return {
        "event_id": str(notification.event_id),
    }


def _deliver_fcm(notification, tokens, credentials_file):
    import firebase_admin
    from firebase_admin import credentials, initialize_app, messaging

    if not firebase_admin._apps:
        options = {}
        project_id = getattr(settings, "FCM_PROJECT_ID", "")
        if project_id:
            options["projectId"] = project_id
        cred = credentials.Certificate(str(credentials_file))
        initialize_app(cred, options or None)

    message = _build_multicast_message(messaging, notification, tokens)
    return messaging.send_each_for_multicast(message)


def _fcm_error_category(exception):
    class_name = exception.__class__.__name__.lower()
    code = str(getattr(exception, "code", "") or "").lower()
    markers = f"{class_name} {code}"
    if any(value in markers for value in ("credential", "auth", "permission", "unauthenticated")):
        return "authentication"
    if any(value in markers for value in ("timeout", "network", "connection", "unavailable")):
        return "transport"
    if any(value in markers for value in ("quota", "rate", "resource-exhausted")):
        return "quota"
    if any(value in markers for value in ("invalid", "argument", "configuration", "valueerror")):
        return "configuration"
    return "unknown"


def _channel_id_for_notification(notification):
    notification_type = str(notification.notification_type).strip()
    return FCM_CHANNEL_IDS.get(notification_type, "overdue")


def _credentials_file():
    configured_path = str(getattr(settings, "FCM_CREDENTIALS_FILE", "")).strip()
    if not configured_path:
        return None
    try:
        path = Path(configured_path).expanduser()
        return path if path.is_file() else None
    except OSError:
        return None
