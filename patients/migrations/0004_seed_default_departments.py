from django.db import migrations


def seed_departments(apps, schema_editor):
    DepartmentConfig = apps.get_model("patients", "DepartmentConfig")
    defaults = [
        {
            "name": "ANC",
            "predefined_actions": ["ANC Visit", "USG Review", "BP & Labs"],
            "metadata_template": {"lmp": "Date", "edd": "Date"},
        },
        {
            "name": "Surgery",
            "predefined_actions": ["LAB TEST", "Xray", "ECG", "Inform Anesthetist"],
            "metadata_template": {"surgical_pathway": "String", "surgery_date": "Date"},
        },
        {
            "name": "Non Surgical",
            "predefined_actions": ["Consultant Review", "Opinion for other consultant"],
            "metadata_template": {"review_date": "Date", "review_frequency": "String"},
        },
    ]
    for item in defaults:
        DepartmentConfig.objects.get_or_create(
            name=item["name"],
            defaults={
                "predefined_actions": item["predefined_actions"],
                "metadata_template": item["metadata_template"],
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0003_case_edd_case_lmp_case_review_date_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_departments, migrations.RunPython.noop),
    ]
