from django.db import migrations


BATCH_SIZE = 500


def normalize_case_name(value):
    normalized = " ".join((value or "").split())
    if not normalized:
        return ""
    return normalized.title()


def normalize_existing_case_names(apps, schema_editor):
    Case = apps.get_model("patients", "Case")
    pending_updates = []

    for case in Case.objects.all().iterator(chunk_size=BATCH_SIZE):
        first_name = normalize_case_name(case.first_name)
        last_name = normalize_case_name(case.last_name)
        patient_name = f"{first_name} {last_name}".strip()

        if (
            first_name == case.first_name
            and last_name == case.last_name
            and patient_name == case.patient_name
        ):
            continue

        case.first_name = first_name
        case.last_name = last_name
        case.patient_name = patient_name
        pending_updates.append(case)

        if len(pending_updates) >= BATCH_SIZE:
            Case.objects.bulk_update(
                pending_updates,
                ["first_name", "last_name", "patient_name"],
                batch_size=BATCH_SIZE,
            )
            pending_updates = []

    if pending_updates:
        Case.objects.bulk_update(
            pending_updates,
            ["first_name", "last_name", "patient_name"],
            batch_size=BATCH_SIZE,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0019_rename_non_surgical_department_to_medicine"),
    ]

    operations = [
        migrations.RunPython(normalize_existing_case_names, migrations.RunPython.noop),
    ]
