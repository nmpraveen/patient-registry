import hashlib

from django.contrib import admin

from .models import MobileDeviceToken, MobileNotification, MobileWriteReceipt


@admin.register(MobileDeviceToken)
class MobileDeviceTokenAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "platform", "app_version", "device_label", "token_fingerprint", "is_active", "last_seen_at")
    search_fields = ("user__username", "device_label")
    list_filter = ("platform", "is_active")
    readonly_fields = ("token_fingerprint", "created_at", "updated_at", "last_seen_at")
    fields = (
        "user",
        "platform",
        "app_version",
        "device_label",
        "token_fingerprint",
        "is_active",
        "last_seen_at",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Token fingerprint")
    def token_fingerprint(self, obj):
        if not obj or not obj.token:
            return ""
        return hashlib.sha256(obj.token.encode("utf-8")).hexdigest()[:12]


@admin.register(MobileNotification)
class MobileNotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "notification_type", "title", "case", "task", "read_at", "created_at")
    search_fields = ("user__username", "title", "body")
    list_filter = ("notification_type", "read_at", "created_at")


@admin.register(MobileWriteReceipt)
class MobileWriteReceiptAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "client_write_id", "write_type", "status", "response_status", "created_at")
    search_fields = ("user__username", "client_write_id", "write_type")
    list_filter = ("write_type", "status")
