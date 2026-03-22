from django.db import migrations


NAV_TOKEN_UPDATES = (
    (("nav", "bg"), "#3949ab", "#fffdf8"),
    (("nav", "text"), "#ffffff", "#1e3a5f"),
    (("nav", "control_text"), "#ffffff", "#6a7280"),
    (("nav", "control_border"), "#c5cae9", "#dfe4ea"),
    (("nav", "control_bg"), "#5c6bc0", "#f3f5f7"),
    (("nav", "control_hover_bg"), "#7986cb", "#e9edf2"),
    (("nav", "logout_bg"), "#ffffff", "#f3f5f7"),
    (("nav", "logout_text"), "#1a237e", "#6a7280"),
)


def update_navbar_defaults(apps, schema_editor):
    ThemeSettings = apps.get_model("patients", "ThemeSettings")

    for theme_settings in ThemeSettings.objects.all():
        tokens = theme_settings.tokens if isinstance(theme_settings.tokens, dict) else {}
        changed = False

        for path, old_value, new_value in NAV_TOKEN_UPDATES:
            current = tokens
            for key in path[:-1]:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(key)
            if not isinstance(current, dict):
                continue

            leaf = path[-1]
            if str(current.get(leaf, "")).strip().lower() == old_value:
                current[leaf] = new_value
                changed = True

        if changed:
            theme_settings.tokens = tokens
            theme_settings.save(update_fields=["tokens"])


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0024_update_theme_palette_defaults"),
    ]

    operations = [
        migrations.RunPython(update_navbar_defaults, noop_reverse),
    ]
