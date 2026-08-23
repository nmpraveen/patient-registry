from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0035_alter_case_prefix_alter_patient_prefix"),
    ]

    operations = [
        migrations.DeleteModel(name="UserAdminNote"),
    ]
