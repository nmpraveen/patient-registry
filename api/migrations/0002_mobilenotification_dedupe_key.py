from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="mobilenotification",
            name="dedupe_key",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddIndex(
            model_name="mobilenotification",
            index=models.Index(fields=["dedupe_key"], name="api_mobilen_dedupe__55933e_idx"),
        ),
        migrations.AddConstraint(
            model_name="mobilenotification",
            constraint=models.UniqueConstraint(
                condition=~models.Q(dedupe_key=""),
                fields=("user", "dedupe_key"),
                name="uniq_mobile_notification_user_dedupe",
            ),
        ),
    ]
