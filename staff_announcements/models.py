from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Announcement(models.Model):
    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Important"
        URGENT = "urgent", "Urgent"

    class Audience(models.TextChoices):
        ALL_STAFF = "all_staff", "All staff"
        SELECTED_ROLES = "selected_roles", "Selected roles"

    text = models.TextField(max_length=2000)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.NORMAL)
    audience = models.CharField(max_length=20, choices=Audience.choices)
    audience_roles = models.ManyToManyField("patients.RoleSetting", blank=True)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(db_index=True)
    publisher = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-starts_at", "-pk")
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="staff_announcement_end_after_start"),
        ]
