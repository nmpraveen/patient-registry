import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


MOBILE_NOTIFICATION_RETENTION_DAYS = 30


def mobile_notification_expiry():
    return timezone.now() + timedelta(days=MOBILE_NOTIFICATION_RETENTION_DAYS)


class MobileDatasetState(models.Model):
    """Singleton epoch separating receipts and device state across dataset replacement."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    epoch = models.UUIDField(default=uuid.uuid4, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class MobileNotificationState(models.Model):
    """Per-account snapshot generation advanced whenever visible events may change."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_notification_state",
    )
    epoch = models.UUIDField(default=uuid.uuid4, editable=False)
    updated_at = models.DateTimeField(auto_now=True)


class MobileOpaqueCursor(models.Model):
    """Short-lived server-side state addressed by a random, non-reversible token."""

    token_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mobile_opaque_cursors",
    )
    kind = models.CharField(max_length=48)
    binding_hash = models.CharField(max_length=64)
    context_hash = models.CharField(max_length=64)
    state = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "kind", "-created_at"], name="api_cursor_user_kind_idx"),
            models.Index(fields=["expires_at"], name="api_cursor_expires_idx"),
        ]


class MobileDeviceToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mobile_device_tokens")
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=32, default="android")
    app_version = models.CharField(max_length=64, blank=True)
    device_label = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["token"]),
        ]

    def __str__(self):
        return f"{self.user} {self.platform} device"


class MobileNotificationType(models.TextChoices):
    ASSIGNMENT = "assignment", "Assignment"
    RED_FLAG = "red_flag", "Red flag"
    OVERDUE = "overdue", "Overdue"


class MobileNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mobile_notifications")
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    notification_type = models.CharField(max_length=32, choices=MobileNotificationType.choices)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    case = models.ForeignKey("patients.Case", on_delete=models.SET_NULL, null=True, blank=True, related_name="mobile_notifications")
    task = models.ForeignKey("patients.Task", on_delete=models.SET_NULL, null=True, blank=True, related_name="mobile_notifications")
    dedupe_key = models.CharField(max_length=160, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(default=mobile_notification_expiry)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "read_at", "-created_at"]),
            models.Index(fields=["notification_type"]),
            models.Index(fields=["dedupe_key"]),
            models.Index(fields=["expires_at"], name="api_mobilen_expires_6bc68f_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "dedupe_key"],
                condition=~models.Q(dedupe_key=""),
                name="uniq_mobile_notification_user_dedupe",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        notification_type=MobileNotificationType.ASSIGNMENT,
                        title="MEDTRACK assignment",
                        body="Open MEDTRACK to review an assignment update.",
                    )
                    | models.Q(
                        notification_type=MobileNotificationType.RED_FLAG,
                        title="MEDTRACK priority update",
                        body="Open MEDTRACK to review a priority update.",
                    )
                    | models.Q(
                        notification_type=MobileNotificationType.OVERDUE,
                        title="MEDTRACK task update",
                        body="Open MEDTRACK to review a task update.",
                    )
                ),
                name="mobile_notification_generic_copy",
            ),
        ]

    def __str__(self):
        return self.title

    @staticmethod
    def canonical_copy(notification_type, event_id):
        copy = {
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
        title, body, channel = copy[notification_type]
        return title, body, channel

    def clean(self):
        super().clean()
        try:
            title, body, _channel = self.canonical_copy(self.notification_type, self.event_id)
        except (KeyError, TypeError, ValueError) as exc:
            from django.core.exceptions import ValidationError

            raise ValidationError({"notification_type": "Unsupported notification type."}) from exc
        errors = {}
        if self.title and self.title != title:
            errors["title"] = "Notification presentation must use the generic server copy."
        if self.body and self.body != body:
            errors["body"] = "Notification presentation must use the generic server copy."
        if errors:
            from django.core.exceptions import ValidationError

            raise ValidationError(errors)
        self.title = title
        self.body = body

    def save(self, *args, **kwargs):
        try:
            generic_title, generic_body, _channel = self.canonical_copy(
                self.notification_type,
                self.event_id,
            )
        except KeyError:
            generic_title = generic_body = ""
        if not self.title:
            self.title = generic_title
        if not self.body:
            self.body = generic_body
        self.full_clean()
        super().save(*args, **kwargs)


class MobileWriteReceipt(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPLIED = "applied"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_FAILED, "Failed"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mobile_write_receipts")
    client_write_id = models.CharField(max_length=80)
    operation = models.CharField(max_length=48)
    target_type = models.CharField(max_length=32)
    target_id = models.CharField(max_length=64, blank=True)
    payload_hash = models.CharField(max_length=64)
    authorization_hash = models.CharField(max_length=64)
    dataset_epoch = models.UUIDField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_metadata = models.JSONField(default=dict, blank=True)
    result_type = models.CharField(max_length=32, blank=True)
    result_id = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "client_write_id"], name="uniq_mobile_write_receipt_user_client")
        ]
        indexes = [
            models.Index(fields=["user", "operation"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["dataset_epoch"]),
        ]

    def __str__(self):
        return f"{self.operation}:receipt-{self.pk or 'new'}"
