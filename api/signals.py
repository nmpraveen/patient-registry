from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from patients.models import Case, RoleSetting, Task, TaskStatus

from .notifications import (
    bump_notification_epochs,
    handle_task_assignment_change,
    notify_case_red_flag,
    notify_task_assignment,
    notify_task_overdue,
    purge_mobile_artifacts_for_case,
    purge_mobile_artifacts_for_task,
    purge_mobile_notifications_for_task,
    revoke_user_mobile_state,
)


@receiver(pre_save, sender=Task)
def capture_previous_task_assignment(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_assigned_user_id = None
        instance._previous_status = None
        instance._previous_due_date = None
        return
    previous = sender.objects.filter(pk=instance.pk).values("assigned_user_id", "status", "due_date").first()
    instance._previous_assigned_user_id = previous["assigned_user_id"] if previous else None
    instance._previous_status = previous["status"] if previous else None
    instance._previous_due_date = previous["due_date"] if previous else None


@receiver(post_save, sender=Task)
def notify_mobile_task_assignment(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    previous_assigned_user_id = getattr(instance, "_previous_assigned_user_id", None)
    if created or previous_assigned_user_id != instance.assigned_user_id:
        handle_task_assignment_change(instance, previous_assigned_user_id)
        notify_task_assignment(instance)
    terminal_statuses = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    previous_status = getattr(instance, "_previous_status", None)
    if instance.status in terminal_statuses and previous_status not in terminal_statuses:
        purge_mobile_notifications_for_task(instance)
    elif previous_status in terminal_statuses and instance.status not in terminal_statuses:
        notify_task_assignment(instance)
    previous_due_date = getattr(instance, "_previous_due_date", None)
    if previous_due_date is not None and previous_due_date != instance.due_date:
        purge_mobile_notifications_for_task(instance)
        notify_task_assignment(instance)
        notify_task_overdue(instance)


@receiver(pre_delete, sender=Task)
def purge_mobile_task_state(sender, instance, **kwargs):
    purge_mobile_artifacts_for_task(instance)


@receiver(pre_save, sender=Case)
def capture_previous_case_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_has_risk_factors = False
        instance._previous_is_archived = False
        instance._previous_risk_signature = ()
        return
    previous = sender.objects.filter(pk=instance.pk).first()
    instance._previous_has_risk_factors = previous.has_risk_factors if previous else False
    instance._previous_is_archived = previous.is_archived if previous else False
    instance._previous_risk_signature = (
        previous.high_risk,
        tuple(previous.anc_high_risk_reasons or []),
        tuple(previous.ncd_flags or []),
    ) if previous else ()


@receiver(post_save, sender=Case)
def notify_mobile_red_flag(sender, instance, raw=False, **kwargs):
    if raw:
        return
    if instance.is_archived and not getattr(instance, "_previous_is_archived", False):
        purge_mobile_artifacts_for_case(instance)
        return
    current_risk_signature = (
        instance.high_risk,
        tuple(instance.anc_high_risk_reasons or []),
        tuple(instance.ncd_flags or []),
    )
    if current_risk_signature != getattr(instance, "_previous_risk_signature", ()):
        notification_users = list(
            instance.mobile_notifications.filter(notification_type="red_flag")
            .values_list("user_id", flat=True)
            .distinct()
        )
        instance.mobile_notifications.filter(notification_type="red_flag").delete()
        bump_notification_epochs(notification_users)
    if instance.has_risk_factors and current_risk_signature != getattr(instance, "_previous_risk_signature", ()):
        notify_case_red_flag(instance)


@receiver(pre_delete, sender=Case)
def purge_mobile_case_state(sender, instance, **kwargs):
    purge_mobile_artifacts_for_case(instance)


@receiver(post_save, sender=RoleSetting)
def revoke_mobile_state_after_role_policy_change(sender, instance, **kwargs):
    user_ids = Group.objects.filter(name=instance.role_name).values_list("user__pk", flat=True)
    revoke_user_mobile_state(user_ids)


@receiver(post_delete, sender=RoleSetting)
def revoke_mobile_state_after_role_policy_delete(sender, instance, **kwargs):
    user_ids = Group.objects.filter(name=instance.role_name).values_list("user__pk", flat=True)
    revoke_user_mobile_state(user_ids)


@receiver(m2m_changed, sender=get_user_model().groups.through)
def revoke_mobile_state_after_group_change(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "pre_clear":
        if reverse:
            instance._mobile_preclear_user_ids = list(instance.user_set.values_list("pk", flat=True))
        else:
            instance._mobile_preclear_user_ids = [instance.pk]
        return
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if reverse:
        user_ids = pk_set or getattr(instance, "_mobile_preclear_user_ids", [])
    else:
        user_ids = [instance.pk]
    revoke_user_mobile_state(user_ids)


@receiver(pre_delete, sender=Group)
def capture_mobile_users_before_group_delete(sender, instance, **kwargs):
    instance._mobile_deleted_group_user_ids = list(instance.user_set.values_list("pk", flat=True))


@receiver(post_delete, sender=Group)
def revoke_mobile_state_after_group_delete(sender, instance, **kwargs):
    revoke_user_mobile_state(getattr(instance, "_mobile_deleted_group_user_ids", []))
