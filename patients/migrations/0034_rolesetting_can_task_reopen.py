from django.db import migrations, models


def enable_task_reopen_for_default_senior_roles(apps, schema_editor):
    RoleSetting = apps.get_model("patients", "RoleSetting")
    RoleSetting.objects.filter(role_name__in=["Admin", "Doctor"]).update(can_task_reopen=True)


def disable_task_reopen_for_default_senior_roles(apps, schema_editor):
    RoleSetting = apps.get_model("patients", "RoleSetting")
    RoleSetting.objects.filter(role_name__in=["Admin", "Doctor"]).update(can_task_reopen=False)


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0033_remove_quote_cost_access_and_clear_quoted_cost"),
    ]

    operations = [
        migrations.AddField(
            model_name="rolesetting",
            name="can_task_reopen",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            enable_task_reopen_for_default_senior_roles,
            disable_task_reopen_for_default_senior_roles,
        ),
    ]
