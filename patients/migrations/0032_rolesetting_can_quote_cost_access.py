from django.db import migrations, models


def enable_default_quote_cost_roles(apps, schema_editor):
    RoleSetting = apps.get_model("patients", "RoleSetting")
    RoleSetting.objects.filter(role_name__in=["Admin", "Doctor"]).update(can_quote_cost_access=True)


def disable_default_quote_cost_roles(apps, schema_editor):
    RoleSetting = apps.get_model("patients", "RoleSetting")
    RoleSetting.objects.update(can_quote_cost_access=False)


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0031_case_blood_group_patient_blood_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="rolesetting",
            name="can_quote_cost_access",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(enable_default_quote_cost_roles, disable_default_quote_cost_roles),
    ]
