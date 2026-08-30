from copy import deepcopy

from django.db import migrations


TOKEN_UPDATES = (
    (("shell", "link"), "#1e88e5", "#0b5cad"),
    (("nav", "control_text"), "#656d7b", "#646c7a"),
    (("buttons", "primary", "text"), "#0d47a1", "#073763"),
    (("buttons", "warning", "text"), "#bf360c", "#7f1d1d"),
    (("buttons", "danger", "text"), "#b71c1c", "#7f1d1d"),
    (("alerts", "warning", "text"), "#bf360c", "#b8320a"),
    (("task_status", "awaiting_reports", "text"), "#bf360c", "#b8320a"),
    (("vitals_status", "high", "text"), "#bf360c", "#b8320a"),
    (("search", "gender_female", "text"), "#c2185b", "#9c3f3f"),
    (("search", "gender_male", "text"), "#1565c0", "#315f86"),
    (("search", "gender_other", "text"), "#6d4c41", "#655c55"),
)

OUTLINE_DEFAULTS = {
    "primary": "#0b5cad",
    "success": "#00695c",
    "secondary": "#4a148c",
    "warning": "#8a2c0b",
    "danger": "#8b1e1e",
    "light": "#1a237e",
}


def _value_at_path(tokens, path):
    current = tokens
    for key in path[:-1]:
        if not isinstance(current, dict):
            return None, None
        current = current.get(key)
    return current, path[-1]


def apply_accessible_defaults(apps, schema_editor):
    ThemeSettings = apps.get_model("patients", "ThemeSettings")
    DepartmentConfig = apps.get_model("patients", "DepartmentConfig")

    for theme_settings in ThemeSettings.objects.all():
        tokens = deepcopy(theme_settings.tokens) if isinstance(theme_settings.tokens, dict) else {}
        changed = False
        for path, old_value, new_value in TOKEN_UPDATES:
            parent, key = _value_at_path(tokens, path)
            if isinstance(parent, dict) and parent.get(key, "").lower() == old_value:
                parent[key] = new_value
                changed = True

        shell = tokens.setdefault("shell", {})
        if "focus_indicator" not in shell:
            shell["focus_indicator"] = "#0b5cad"
            changed = True
        buttons = tokens.setdefault("buttons", {})
        for name, outline_text in OUTLINE_DEFAULTS.items():
            button = buttons.setdefault(name, {})
            if "outline_text" not in button:
                button["outline_text"] = outline_text
                changed = True

        if changed:
            theme_settings.tokens = tokens
            theme_settings.save(update_fields=["tokens"])

    DepartmentConfig.objects.filter(
        name__iexact="ANC",
        theme_bg_color__iexact="#ffe0b2",
        theme_text_color__iexact="#bf360c",
    ).update(theme_text_color="#b8320a")


def restore_previous_defaults(apps, schema_editor):
    ThemeSettings = apps.get_model("patients", "ThemeSettings")
    DepartmentConfig = apps.get_model("patients", "DepartmentConfig")

    for theme_settings in ThemeSettings.objects.all():
        tokens = deepcopy(theme_settings.tokens) if isinstance(theme_settings.tokens, dict) else {}
        changed = False
        for path, old_value, new_value in TOKEN_UPDATES:
            parent, key = _value_at_path(tokens, path)
            if isinstance(parent, dict) and parent.get(key, "").lower() == new_value:
                parent[key] = old_value
                changed = True
        for button in tokens.get("buttons", {}).values():
            if isinstance(button, dict) and "outline_text" in button:
                button.pop("outline_text")
                changed = True
        if tokens.get("shell", {}).get("focus_indicator", "").lower() == "#0b5cad":
            tokens["shell"].pop("focus_indicator")
            changed = True
        if changed:
            theme_settings.tokens = tokens
            theme_settings.save(update_fields=["tokens"])

    DepartmentConfig.objects.filter(
        name__iexact="ANC",
        theme_bg_color__iexact="#ffe0b2",
        theme_text_color__iexact="#b8320a",
    ).update(theme_text_color="#bf360c")


class Migration(migrations.Migration):
    dependencies = [("patients", "0037_backend_auth_clinical_security")]

    operations = [
        migrations.RunPython(apply_accessible_defaults, restore_previous_defaults),
    ]
