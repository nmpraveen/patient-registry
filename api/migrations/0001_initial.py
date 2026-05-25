from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("patients", "0035_alter_case_prefix_alter_patient_prefix"),
    ]

    operations = [
        migrations.CreateModel(
            name="MobileDeviceToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=255, unique=True)),
                ("platform", models.CharField(default="android", max_length=32)),
                ("app_version", models.CharField(blank=True, max_length=64)),
                ("device_label", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mobile_device_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MobileNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "notification_type",
                    models.CharField(
                        choices=[
                            ("assignment", "Assignment"),
                            ("red_flag", "Red flag"),
                            ("overdue", "Overdue"),
                        ],
                        max_length=32,
                    ),
                ),
                ("title", models.CharField(max_length=160)),
                ("body", models.TextField(blank=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "case",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mobile_notifications",
                        to="patients.case",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mobile_notifications",
                        to="patients.task",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mobile_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="MobileWriteReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("client_write_id", models.CharField(max_length=80)),
                ("write_type", models.CharField(max_length=32)),
                ("status", models.CharField(default="applied", max_length=16)),
                ("response_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mobile_write_receipts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="mobiledevicetoken",
            index=models.Index(fields=["user", "is_active"], name="api_mobiled_user_id_3ba6c8_idx"),
        ),
        migrations.AddIndex(
            model_name="mobiledevicetoken",
            index=models.Index(fields=["token"], name="api_mobiled_token_d46811_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilenotification",
            index=models.Index(fields=["user", "read_at", "-created_at"], name="api_mobilen_user_id_db3845_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilenotification",
            index=models.Index(fields=["notification_type"], name="api_mobilen_notific_f6c3ac_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilewritereceipt",
            index=models.Index(fields=["user", "write_type"], name="api_mobilew_user_id_26b942_idx"),
        ),
        migrations.AddConstraint(
            model_name="mobilewritereceipt",
            constraint=models.UniqueConstraint(
                fields=("user", "client_write_id"),
                name="uniq_mobile_write_receipt_user_client",
            ),
        ),
    ]
