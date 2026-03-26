from django.db import migrations


def clear_quoted_cost_metadata(apps, schema_editor):
    Case = apps.get_model("patients", "Case")

    cases_to_update = []
    for case in Case.objects.filter(metadata__has_key="quoted_cost").only("id", "metadata"):
        metadata = dict(case.metadata or {})
        if "quoted_cost" not in metadata:
            continue
        metadata.pop("quoted_cost", None)
        case.metadata = metadata
        cases_to_update.append(case)

    if cases_to_update:
        Case.objects.bulk_update(cases_to_update, ["metadata"])


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0032_rolesetting_can_quote_cost_access"),
    ]

    operations = [
        migrations.RunPython(clear_quoted_cost_metadata, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="rolesetting",
            name="can_quote_cost_access",
        ),
    ]
