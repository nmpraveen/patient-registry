from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("patients", "0045_rolesetting_can_manage_phonebook")]
    operations = [
        migrations.CreateModel(
            name="AuditEvidenceExportAck",
            fields=[
                ("event_id", models.UUIDField(primary_key=True, serialize=False)),
                ("segment_sequence", models.PositiveBigIntegerField(db_index=True)),
                ("segment_chain_sha256", models.CharField(max_length=64)),
                ("segment_name", models.CharField(max_length=64)),
                ("acknowledged_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="AuditEvidenceExportState",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("segment_sequence", models.PositiveBigIntegerField()),
                ("segment_chain_sha256", models.CharField(max_length=64)),
            ],
        ),
    ]
