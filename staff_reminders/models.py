from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models


class Reminder(models.Model):
    class Recurrence(models.TextChoices):
        ONCE = "ONCE", "Once"
        MONTHLY = "MONTHLY", "Monthly"
        EVERY_TWO_MONTHS = "EVERY_TWO_MONTHS", "Every two months"
        YEARLY = "YEARLY", "Yearly"

    title = models.CharField(max_length=200)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_staff_reminders")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assigned_staff_reminders")
    due_date = models.DateField()
    advance_notice_days = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(365)])
    recurrence = models.CharField(max_length=20, choices=Recurrence.choices, default=Recurrence.ONCE)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    next_index = models.PositiveIntegerField(default=1, editable=False)
    next_notice_date = models.DateField(null=True, editable=False, db_index=True)
    last_scheduled_at = models.DateTimeField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(advance_notice_days__lte=365), name="reminder_notice_max365")]


class ReminderOccurrence(models.Model):
    reminder = models.ForeignKey(Reminder, on_delete=models.PROTECT, related_name="occurrences")
    index = models.PositiveIntegerField()
    due_date = models.DateField()
    notice_date = models.DateField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["reminder", "index"], name="reminder_occurrence_index_unique"),
            models.UniqueConstraint(fields=["reminder", "due_date"], name="reminder_occurrence_date_unique"),
            models.CheckConstraint(condition=(models.Q(completed_at__isnull=True, completed_by__isnull=True) | models.Q(completed_at__isnull=False, completed_by__isnull=False)), name="reminder_completion_pair"),
        ]
