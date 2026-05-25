from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0002_mobilenotification_dedupe_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="mobilewritereceipt",
            name="response_status",
            field=models.PositiveSmallIntegerField(default=200),
        ),
    ]
