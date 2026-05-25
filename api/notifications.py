import hashlib

from django.db import IntegrityError, transaction
from django.utils import timezone

from patients.models import TaskStatus

from .models import MobileNotification, MobileNotificationType
from .push import send_mobile_notification


def create_mobile_notification(
    *,
    user,
    notification_type,
    title,
    body="",
    case=None,
    task=None,
    payload=None,
    dedupe_key="",
):
    if not user or not getattr(user, "is_active", True):
        return None

    payload = {
        "type": notification_type,
        "case_id": case.pk if case else None,
        "task_id": task.pk if task else None,
        **(payload or {}),
    }
    defaults = {
        "notification_type": notification_type,
        "title": title[:160],
        "body": body,
        "case": case,
        "task": task,
        "payload": payload,
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
        transaction.on_commit(lambda: send_mobile_notification(notification))
    return notification


def notify_task_assignment(task):
    if not task.assigned_user_id or task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
        return None
    case = task.case
    due_label = task.due_date.strftime("%d %b %Y") if task.due_date else ""
    return create_mobile_notification(
        user=task.assigned_user,
        notification_type=MobileNotificationType.ASSIGNMENT,
        title="New MEDTRACK assignment",
        body=f"{case.full_name or case.patient_name}: {task.title} due {due_label}".strip(),
        case=case,
        task=task,
        payload={"channel": "assignments", "due_date": task.due_date.isoformat() if task.due_date else ""},
        dedupe_key=f"assignment:task:{task.pk}:user:{task.assigned_user_id}",
    )


def notify_case_red_flag(case):
    recipients = _case_notification_recipients(case)
    if not recipients:
        return []
    reasons = _risk_reasons(case)
    reason_text = ", ".join(reasons) if reasons else "Risk factor flagged"
    signature = _dedupe_hash("|".join(reasons) or "flagged")
    notifications = []
    for user in recipients:
        notification = create_mobile_notification(
            user=user,
            notification_type=MobileNotificationType.RED_FLAG,
            title="Red flag patient",
            body=f"{case.full_name or case.patient_name}: {reason_text}",
            case=case,
            payload={"channel": "red_flags", "reasons": reasons},
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
    days_overdue = (as_of - task.due_date).days
    day_unit = "day" if days_overdue == 1 else "days"
    case = task.case
    return create_mobile_notification(
        user=task.assigned_user,
        notification_type=MobileNotificationType.OVERDUE,
        title="Overdue MEDTRACK task",
        body=f"{case.full_name or case.patient_name}: {task.title} is {days_overdue} {day_unit} overdue",
        case=case,
        task=task,
        payload={
            "channel": "overdue",
            "due_date": task.due_date.isoformat(),
            "days_overdue": days_overdue,
        },
        dedupe_key=f"overdue:task:{task.pk}:user:{task.assigned_user_id}:date:{as_of.isoformat()}",
    )


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
