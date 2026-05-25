from django.conf import settings
from django.db import models


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
    notification_type = models.CharField(max_length=32, choices=MobileNotificationType.choices)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    case = models.ForeignKey("patients.Case", on_delete=models.SET_NULL, null=True, blank=True, related_name="mobile_notifications")
    task = models.ForeignKey("patients.Task", on_delete=models.SET_NULL, null=True, blank=True, related_name="mobile_notifications")
    payload = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=160, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "read_at", "-created_at"]),
            models.Index(fields=["notification_type"]),
            models.Index(fields=["dedupe_key"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "dedupe_key"],
                condition=~models.Q(dedupe_key=""),
                name="uniq_mobile_notification_user_dedupe",
            ),
        ]

    def __str__(self):
        return self.title


class MobileWriteReceipt(models.Model):
    STATUS_APPLIED = "applied"
    STATUS_FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mobile_write_receipts")
    client_write_id = models.CharField(max_length=80)
    write_type = models.CharField(max_length=32)
    status = models.CharField(max_length=16, default=STATUS_APPLIED)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "client_write_id"], name="uniq_mobile_write_receipt_user_client")
        ]
        indexes = [
            models.Index(fields=["user", "write_type"]),
        ]

    def __str__(self):
        return f"{self.write_type}:{self.client_write_id}"
