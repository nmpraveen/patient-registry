from django.db import migrations, models


def backfill_client_event_time(apps, schema_editor):
    CallLog = apps.get_model("patients", "CallLog")
    for call_log in CallLog.objects.filter(client_event_at__isnull=True).iterator():
        CallLog.objects.filter(pk=call_log.pk).update(client_event_at=call_log.created_at)


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0036_remove_plaintext_password_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="calllog",
            name="client_event_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_client_event_time, migrations.RunPython.noop),
    ]
