from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from patients.models import Case, Task

from .notifications import notify_case_red_flag, notify_task_assignment


@receiver(pre_save, sender=Task)
def capture_previous_task_assignment(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_assigned_user_id = None
        return
    instance._previous_assigned_user_id = (
        sender.objects.filter(pk=instance.pk).values_list("assigned_user_id", flat=True).first()
    )


@receiver(post_save, sender=Task)
def notify_mobile_task_assignment(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    previous_assigned_user_id = getattr(instance, "_previous_assigned_user_id", None)
    if created or previous_assigned_user_id != instance.assigned_user_id:
        notify_task_assignment(instance)


@receiver(pre_save, sender=Case)
def capture_previous_case_risk(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_has_risk_factors = False
        return
    previous = sender.objects.filter(pk=instance.pk).first()
    instance._previous_has_risk_factors = previous.has_risk_factors if previous else False


@receiver(post_save, sender=Case)
def notify_mobile_red_flag(sender, instance, raw=False, **kwargs):
    if raw:
        return
    if instance.has_risk_factors and not getattr(instance, "_previous_has_risk_factors", False):
        notify_case_red_flag(instance)
