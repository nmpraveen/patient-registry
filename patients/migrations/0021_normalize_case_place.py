from django.db import migrations


BATCH_SIZE = 500


def normalize_case_name(value):
    normalized = " ".join((value or "").split())
    if not normalized:
        return ""
    return normalized.title()


def normalize_existing_case_places(apps, schema_editor):
    Case = apps.get_model("patients", "Case")
    pending_updates = []

    for case in Case.objects.all().iterator(chunk_size=BATCH_SIZE):
        place = normalize_case_name(case.place)
        if place == case.place:
            continue

        case.place = place
        pending_updates.append(case)

        if len(pending_updates) >= BATCH_SIZE:
            Case.objects.bulk_update(
                pending_updates,
                ["place"],
                batch_size=BATCH_SIZE,
            )
            pending_updates = []

    if pending_updates:
        Case.objects.bulk_update(
            pending_updates,
            ["place"],
            batch_size=BATCH_SIZE,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0020_normalize_case_names"),
    ]

    operations = [
        migrations.RunPython(normalize_existing_case_places, migrations.RunPython.noop),
    ]
