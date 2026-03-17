from django.db import migrations


LEGACY_MEDICINE_NAMES = ("Non Surgical", "Non-Surgical", "Nonsurgical")
MEDICINE_NAME = "Medicine"
MEDICINE_PREDEFINED_ACTIONS = ["Consultant Review", "Opinion for other consultant"]
MEDICINE_METADATA_TEMPLATE = {"review_date": "Date", "review_frequency": "String"}
MEDICINE_THEME_BG = "#e2e3e5"
MEDICINE_THEME_TEXT = "#41464b"


def _merge_missing_values(target, source):
    updated_fields = []
    if not target.predefined_actions and source.predefined_actions:
        target.predefined_actions = list(source.predefined_actions)
        updated_fields.append("predefined_actions")
    if not target.metadata_template and source.metadata_template:
        target.metadata_template = dict(source.metadata_template)
        updated_fields.append("metadata_template")
    if not target.theme_bg_color and source.theme_bg_color:
        target.theme_bg_color = source.theme_bg_color
        updated_fields.append("theme_bg_color")
    if not target.theme_text_color and source.theme_text_color:
        target.theme_text_color = source.theme_text_color
        updated_fields.append("theme_text_color")
    return updated_fields


def _ensure_medicine_defaults(department):
    updated_fields = []
    if not department.predefined_actions:
        department.predefined_actions = list(MEDICINE_PREDEFINED_ACTIONS)
        updated_fields.append("predefined_actions")
    if not department.metadata_template:
        department.metadata_template = dict(MEDICINE_METADATA_TEMPLATE)
        updated_fields.append("metadata_template")
    if not department.theme_bg_color:
        department.theme_bg_color = MEDICINE_THEME_BG
        updated_fields.append("theme_bg_color")
    if not department.theme_text_color:
        department.theme_text_color = MEDICINE_THEME_TEXT
        updated_fields.append("theme_text_color")
    return updated_fields


def rename_non_surgical_department(apps, schema_editor):
    DepartmentConfig = apps.get_model("patients", "DepartmentConfig")
    Case = apps.get_model("patients", "Case")

    legacy_departments = list(DepartmentConfig.objects.filter(name__in=LEGACY_MEDICINE_NAMES).order_by("id"))
    medicine = DepartmentConfig.objects.filter(name=MEDICINE_NAME).first()

    if medicine is None and legacy_departments:
        medicine = legacy_departments.pop(0)
        medicine.name = MEDICINE_NAME
        update_fields = ["name"]
        update_fields.extend(_ensure_medicine_defaults(medicine))
        medicine.save(update_fields=sorted(set(update_fields)))
    elif medicine is None:
        medicine = DepartmentConfig.objects.create(
            name=MEDICINE_NAME,
            predefined_actions=list(MEDICINE_PREDEFINED_ACTIONS),
            metadata_template=dict(MEDICINE_METADATA_TEMPLATE),
            theme_bg_color=MEDICINE_THEME_BG,
            theme_text_color=MEDICINE_THEME_TEXT,
        )

    for legacy in legacy_departments:
        update_fields = _merge_missing_values(medicine, legacy)
        update_fields.extend(_ensure_medicine_defaults(medicine))
        if update_fields:
            medicine.save(update_fields=sorted(set(update_fields)))
        Case.objects.filter(category_id=legacy.id).update(category_id=medicine.id)
        legacy.delete()

    update_fields = _ensure_medicine_defaults(medicine)
    if update_fields:
        medicine.save(update_fields=sorted(set(update_fields)))


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0018_useradminnote"),
    ]

    operations = [
        migrations.RunPython(rename_non_surgical_department, migrations.RunPython.noop),
    ]
