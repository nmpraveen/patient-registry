import uuid

from django.db import migrations, models
from django.utils import timezone


def purge_legacy_phi_mobile_state(apps, schema_editor):
    apps.get_model("api", "MobileNotification").objects.all().delete()
    apps.get_model("api", "MobileWriteReceipt").objects.all().delete()
    apps.get_model("api", "MobileDeviceToken").objects.filter(is_active=True).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0003_mobilewritereceipt_response_status"),
        ("patients", "0037_calllog_client_event_at"),
    ]

    operations = [
        migrations.RunPython(purge_legacy_phi_mobile_state, migrations.RunPython.noop),
        migrations.CreateModel(
            name="MobileDatasetState",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("epoch", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name="mobilenotification",
            name="event_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.RemoveIndex(
            model_name="mobilewritereceipt",
            name="api_mobilew_user_id_26b942_idx",
        ),
        migrations.RenameField(
            model_name="mobilewritereceipt",
            old_name="write_type",
            new_name="operation",
        ),
        migrations.RenameField(
            model_name="mobilewritereceipt",
            old_name="response_payload",
            new_name="response_metadata",
        ),
        migrations.AddField(
            model_name="mobilewritereceipt",
            name="authorization_hash",
            field=models.CharField(default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="mobilewritereceipt",
            name="dataset_epoch",
            field=models.UUIDField(default=uuid.uuid4),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="mobilewritereceipt",
            name="expires_at",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="mobilewritereceipt",
            name="payload_hash",
            field=models.CharField(default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="mobilewritereceipt",
            name="result_id",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="mobilewritereceipt",
            name="result_type",
            field=models.CharField(blank=True, default="", max_length=32),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="mobilewritereceipt",
            name="target_id",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="mobilewritereceipt",
            name="target_type",
            field=models.CharField(default="", max_length=32),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="mobilewritereceipt",
            name="operation",
            field=models.CharField(max_length=48),
        ),
        migrations.AlterField(
            model_name="mobilewritereceipt",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("applied", "Applied"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddIndex(
            model_name="mobilewritereceipt",
            index=models.Index(fields=["user", "operation"], name="api_mobilew_user_id_f3e608_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilewritereceipt",
            index=models.Index(fields=["expires_at"], name="api_mobilew_expires_7af228_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilewritereceipt",
            index=models.Index(fields=["dataset_epoch"], name="api_mobilew_dataset_35cd43_idx"),
        ),
    ]
