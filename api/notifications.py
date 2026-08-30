import hashlib
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from patients.models import TaskStatus

from .models import (
    MobileDatasetState,
    MobileDeviceToken,
    MobileNotification,
    MobileNotificationType,
    MobileWriteReceipt,
)
from .push import send_mobile_notification


_notifications_suspended = ContextVar("mobile_notifications_suspended", default=False)
GENERIC_NOTIFICATION_COPY = {
    MobileNotificationType.ASSIGNMENT: (
        "MEDTRACK assignment",
        "Open MEDTRACK to review an assignment update.",
        "assignments",
    ),
    MobileNotificationType.RED_FLAG: (
        "MEDTRACK priority update",
        "Open MEDTRACK to review a priority update.",
        "red_flags",
    ),
    MobileNotificationType.OVERDUE: (
        "MEDTRACK task update",
        "Open MEDTRACK to review a task update.",
        "overdue",
    ),
}


@contextmanager
def suspend_mobile_notifications():
    token = _notifications_suspended.set(True)
    try:
        yield
    finally:
        _notifications_suspended.reset(token)


def create_mobile_notification(
    *,
    user,
    notification_type,
    title="",
    body="",
    case=None,
    task=None,
    payload=None,
    dedupe_key="",
):
    del title, body, payload  # Clinical content must never be persisted or sent through FCM.
    purge_expired_mobile_notifications()
    if _notifications_suspended.get() or not user or not getattr(user, "is_active", True):
        return None
    if case is None or not _user_can_receive_case_notification(
        user,
        case,
        task=task,
        notification_type=notification_type,
    ):
        return None

    generic_title, generic_body, channel = GENERIC_NOTIFICATION_COPY[notification_type]
    event_id = uuid.uuid4()
    defaults = {
        "event_id": event_id,
        "notification_type": notification_type,
        "title": generic_title,
        "body": generic_body,
        "case": case,
        "task": task,
        "payload": {
            "event_id": str(event_id),
            "type": notification_type,
            "channel": channel,
        },
    }

    try:
        if dedupe_key:
            notification, created = MobileNotification.objects.get_or_create(
                user=user,
                dedupe_key=dedupe_key,
                defaults=defaults,
            )
        else:
            notification = MobileNotification.objects.create(user=user, **defaults)
            created = True
    except IntegrityError:
        notification = MobileNotification.objects.filter(user=user, dedupe_key=dedupe_key).first()
        created = False

    if created and notification:
        transaction.on_commit(
            lambda notification_id=notification.pk: _send_notification_if_current(notification_id)
        )
    return notification


def notify_task_assignment(task):
    if not task.assigned_user_id or task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
        return None
    return create_mobile_notification(
        user=task.assigned_user,
        notification_type=MobileNotificationType.ASSIGNMENT,
        case=task.case,
        task=task,
        dedupe_key=f"assignment:task:{task.pk}:user:{task.assigned_user_id}",
    )


def notify_case_red_flag(case):
    recipients = _case_notification_recipients(case)
    if not recipients:
        return []
    signature = _dedupe_hash("|".join(_risk_reasons(case)) or "flagged")
    notifications = []
    for user in recipients:
        notification = create_mobile_notification(
            user=user,
            notification_type=MobileNotificationType.RED_FLAG,
            case=case,
            dedupe_key=f"red_flag:case:{case.pk}:user:{user.pk}:{signature}",
        )
        if notification:
            notifications.append(notification)
    return notifications


def notify_task_overdue(task, *, as_of=None):
    if not task.assigned_user_id or task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
        return None
    as_of = as_of or timezone.localdate()
    if task.due_date >= as_of:
        return None
    return create_mobile_notification(
        user=task.assigned_user,
        notification_type=MobileNotificationType.OVERDUE,
        case=task.case,
        task=task,
        dedupe_key=f"overdue:task:{task.pk}:user:{task.assigned_user_id}:date:{as_of.isoformat()}",
    )


def authorized_notification_queryset(user):
    from patients.views import _accessible_case_queryset

    accessible_case_ids = _accessible_case_queryset(user).values("pk")
    inactive_task_statuses = [TaskStatus.COMPLETED, TaskStatus.CANCELLED]
    return (
        MobileNotification.objects.filter(
            user=user,
            case_id__in=accessible_case_ids,
            expires_at__gt=timezone.now(),
        )
        .filter(
            Q(notification_type=MobileNotificationType.RED_FLAG, task__isnull=True)
            | (Q(task__assigned_user=user) & ~Q(task__status__in=inactive_task_statuses))
        )
    )


def notification_is_authorized(notification):
    if not notification.pk or not notification.user_id:
        return False
    user = notification.user
    if not user.is_active:
        return False
    return authorized_notification_queryset(user).filter(pk=notification.pk).exists()


def purge_stale_notifications_for_user(user):
    authorized_ids = authorized_notification_queryset(user).values("pk")
    return MobileNotification.objects.filter(user=user).exclude(pk__in=authorized_ids).delete()[0]


def revoke_user_mobile_state(user_ids, *, purge_receipts=True):
    normalized_ids = {int(user_id) for user_id in user_ids if user_id}
    if not normalized_ids:
        return
    MobileDeviceToken.objects.filter(user_id__in=normalized_ids, is_active=True).update(is_active=False)
    users = get_user_model().objects.filter(pk__in=normalized_ids)
    for user in users:
        purge_stale_notifications_for_user(user)
    if purge_receipts:
        MobileWriteReceipt.objects.filter(user_id__in=normalized_ids).delete()


def purge_expired_mobile_receipts(*, limit=500, as_of=None):
    """Delete at most ``limit`` expired receipts during ordinary mobile write traffic."""

    bounded_limit = max(1, min(int(limit), 5000))
    expired_ids = list(
        MobileWriteReceipt.objects.filter(expires_at__lte=as_of or timezone.now())
        .order_by("expires_at", "pk")
        .values_list("pk", flat=True)[:bounded_limit]
    )
    if not expired_ids:
        return 0
    return MobileWriteReceipt.objects.filter(pk__in=expired_ids).delete()[0]


def purge_expired_mobile_notifications(*, limit=500, as_of=None):
    """Delete at most ``limit`` expired notifications during ordinary mobile traffic."""

    bounded_limit = max(1, min(int(limit), 5000))
    expired_ids = list(
        MobileNotification.objects.filter(expires_at__lte=as_of or timezone.now())
        .order_by("expires_at", "pk")
        .values_list("pk", flat=True)[:bounded_limit]
    )
    if not expired_ids:
        return 0
    return MobileNotification.objects.filter(pk__in=expired_ids).delete()[0]


def handle_task_assignment_change(task, previous_user_id):
    if _notifications_suspended.get() or previous_user_id == task.assigned_user_id:
        return
    if previous_user_id:
        MobileNotification.objects.filter(user_id=previous_user_id, task_id=task.pk).delete()
        _purge_receipts_for_target_user(previous_user_id, "task", task.pk)
        previous_user = get_user_model().objects.filter(pk=previous_user_id).first()
        if previous_user and not _user_can_access_case(previous_user, task.case):
            MobileNotification.objects.filter(user=previous_user, case=task.case).delete()
            _purge_receipts_for_target_user(previous_user_id, "case", task.case_id)
            MobileDeviceToken.objects.filter(user=previous_user, is_active=True).update(is_active=False)


def purge_mobile_artifacts_for_task(task):
    if _notifications_suspended.get():
        return
    MobileNotification.objects.filter(task_id=task.pk).delete()
    MobileWriteReceipt.objects.filter(
        Q(target_type="task", target_id=str(task.pk))
        | Q(result_type="task", result_id=str(task.pk))
    ).delete()


def purge_mobile_notifications_for_task(task):
    if _notifications_suspended.get():
        return 0
    return MobileNotification.objects.filter(task_id=task.pk).delete()[0]


def purge_mobile_artifacts_for_case(case):
    if _notifications_suspended.get():
        return
    task_ids = [str(value) for value in case.tasks.values_list("pk", flat=True)]
    vital_ids = [str(value) for value in case.vitals.values_list("pk", flat=True)]
    call_ids = [str(value) for value in case.call_logs.values_list("pk", flat=True)]
    MobileNotification.objects.filter(case_id=case.pk).delete()
    receipt_query = Q(target_type="case", target_id=str(case.pk)) | Q(
        result_type="case",
        result_id=str(case.pk),
    )
    if task_ids:
        receipt_query |= Q(target_type="task", target_id__in=task_ids) | Q(
            result_type="task",
            result_id__in=task_ids,
        )
    if vital_ids:
        receipt_query |= Q(result_type="vital", result_id__in=vital_ids)
    if call_ids:
        receipt_query |= Q(result_type="call_log", result_id__in=call_ids)
    MobileWriteReceipt.objects.filter(receipt_query).delete()


@transaction.atomic
def invalidate_mobile_dataset():
    """Atomically advance the epoch and revoke every piece of mobile state."""

    state, _ = MobileDatasetState.objects.select_for_update().get_or_create(pk=1)
    state.epoch = uuid.uuid4()
    state.save(update_fields=["epoch", "updated_at"])
    MobileNotification.objects.all().delete()
    MobileWriteReceipt.objects.all().delete()
    MobileDeviceToken.objects.filter(is_active=True).update(is_active=False)
    return state.epoch


def _send_notification_if_current(notification_id):
    notification = (
        MobileNotification.objects.select_related("user", "case", "task")
        .filter(pk=notification_id)
        .first()
    )
    if notification is None:
        return {"sent": False, "reason": "notification_revoked"}
    return send_mobile_notification(notification)


def _user_can_receive_case_notification(user, case, *, task, notification_type):
    if not _user_can_access_case(user, case):
        return False
    if notification_type in {MobileNotificationType.ASSIGNMENT, MobileNotificationType.OVERDUE}:
        return bool(
            task
            and task.assigned_user_id == user.pk
            and task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
        )
    return True


def _user_can_access_case(user, case):
    from patients.views import _accessible_case_queryset

    return _accessible_case_queryset(user).filter(pk=case.pk).exists()


def _purge_receipts_for_target_user(user_id, target_type, target_id):
    MobileWriteReceipt.objects.filter(
        user_id=user_id,
        target_type=target_type,
        target_id=str(target_id),
    ).delete()


def _case_notification_recipients(case):
    tasks = (
        case.tasks.filter(assigned_user__isnull=False)
        .exclude(status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED])
        .select_related("assigned_user")
        .order_by()
    )
    users = []
    seen_user_ids = set()
    for task in tasks:
        if task.assigned_user_id in seen_user_ids:
            continue
        seen_user_ids.add(task.assigned_user_id)
        users.append(task.assigned_user)
    if not users and case.created_by_id:
        users = [case.created_by]
    return users


def _risk_reasons(case):
    reasons = []
    if case.high_risk:
        reasons.append("High risk")
    reasons.extend(case.anc_high_risk_reason_labels)
    reasons.extend(case.ncd_flag_labels)
    return list(dict.fromkeys(reasons))


def _dedupe_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
