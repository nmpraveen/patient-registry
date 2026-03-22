import re

from django.db import migrations


OLD_CATEGORY_THEME_DEFAULTS = {
    "ANC": {"bg": "#d1e7dd", "text": "#0f5132"},
    "SURGERY": {"bg": "#fff3cd", "text": "#664d03"},
    "MEDICINE": {"bg": "#e2e3e5", "text": "#41464b"},
}

NEW_CATEGORY_THEME_DEFAULTS = {
    "ANC": {"bg": "#ffe0b2", "text": "#bf360c"},
    "SURGERY": {"bg": "#b2dfdb", "text": "#004d40"},
    "MEDICINE": {"bg": "#c5cae9", "text": "#1a237e"},
}

THEME_TOKEN_UPDATES = (
    (("shell", "page_bg"), "#f8f9fa", "#f7f4ef"),
    (("shell", "page_text"), "#212529", "#1f2430"),
    (("shell", "surface_text"), "#212529", "#1f2430"),
    (("shell", "surface_border"), "#dee2e6", "#e5dfd4"),
    (("shell", "muted_text"), "#6c757d", "#6d6a63"),
    (("shell", "link"), "#0d6efd", "#1e88e5"),
    (("shell", "link_hover"), "#0a58ca", "#0d47a1"),
    (("shell", "shadow"), "#000000", "#1a237e"),
    (("nav", "bg"), "#0d6efd", "#3949ab"),
    (("nav", "control_border"), "#ffffff", "#c5cae9"),
    (("nav", "control_bg"), "#2b6fd1", "#5c6bc0"),
    (("nav", "control_hover_bg"), "#3f80db", "#7986cb"),
    (("nav", "logout_bg"), "#f8f9fa", "#ffffff"),
    (("nav", "logout_text"), "#000000", "#1a237e"),
    (("case_header", "bg"), "#0d6efd", "#3949ab"),
    (("buttons", "primary", "bg"), "#0d6efd", "#64b5f6"),
    (("buttons", "primary", "text"), "#ffffff", "#0d47a1"),
    (("buttons", "success", "bg"), "#198754", "#80cbc4"),
    (("buttons", "success", "text"), "#ffffff", "#004d40"),
    (("buttons", "secondary", "bg"), "#6c757d", "#b39ddb"),
    (("buttons", "secondary", "text"), "#ffffff", "#4a148c"),
    (("buttons", "warning", "bg"), "#ffc107", "#ffab91"),
    (("buttons", "warning", "text"), "#000000", "#bf360c"),
    (("buttons", "danger", "bg"), "#dc3545", "#ef9a9a"),
    (("buttons", "danger", "text"), "#ffffff", "#b71c1c"),
    (("buttons", "light", "bg"), "#f8f9fa", "#f7f4ef"),
    (("buttons", "light", "text"), "#000000", "#1a237e"),
    (("alerts", "info", "bg"), "#cff4fc", "#bbdefb"),
    (("alerts", "info", "text"), "#055160", "#0d47a1"),
    (("alerts", "success", "bg"), "#d1e7dd", "#dcedc8"),
    (("alerts", "success", "text"), "#0a3622", "#33691e"),
    (("alerts", "warning", "bg"), "#fff3cd", "#ffe0b2"),
    (("alerts", "warning", "text"), "#664d03", "#bf360c"),
    (("alerts", "danger", "bg"), "#f8d7da", "#ffcdd2"),
    (("alerts", "danger", "text"), "#58151c", "#b71c1c"),
    (("alerts", "light", "bg"), "#fcfcfd", "#f7f4ef"),
    (("alerts", "light", "text"), "#495057", "#5f5a52"),
    (("dashboard", "today", "bg"), "#cfe2ff", "#dcedc8"),
    (("dashboard", "today", "text"), "#052c65", "#33691e"),
    (("dashboard", "recent", "bg"), "#b6d4fe", "#d1c4e9"),
    (("dashboard", "recent", "text"), "#084298", "#4a148c"),
    (("dashboard", "upcoming", "bg"), "#cff4fc", "#bbdefb"),
    (("dashboard", "upcoming", "text"), "#055160", "#0d47a1"),
    (("dashboard", "overdue", "bg"), "#f8d7da", "#ffcdd2"),
    (("dashboard", "overdue", "text"), "#842029", "#b71c1c"),
    (("case_status", "active", "bg"), "#cfe2ff", "#bbdefb"),
    (("case_status", "active", "text"), "#084298", "#0d47a1"),
    (("case_status", "completed", "bg"), "#d1e7dd", "#dcedc8"),
    (("case_status", "completed", "text"), "#0f5132", "#33691e"),
    (("case_status", "cancelled", "bg"), "#f8d7da", "#ffcdd2"),
    (("case_status", "cancelled", "text"), "#842029", "#b71c1c"),
    (("case_status", "loss_to_follow_up", "bg"), "#fff3cd", "#d1c4e9"),
    (("case_status", "loss_to_follow_up", "text"), "#664d03", "#4a148c"),
    (("task_status", "scheduled", "bg"), "#0d6efd", "#bbdefb"),
    (("task_status", "scheduled", "text"), "#ffffff", "#0d47a1"),
    (("task_status", "awaiting_reports", "bg"), "#fd7e14", "#ffe0b2"),
    (("task_status", "awaiting_reports", "text"), "#ffffff", "#bf360c"),
    (("task_status", "completed", "bg"), "#198754", "#dcedc8"),
    (("task_status", "completed", "text"), "#ffffff", "#33691e"),
    (("task_status", "cancelled", "bg"), "#6c757d", "#ffcdd2"),
    (("task_status", "cancelled", "text"), "#ffffff", "#b71c1c"),
    (("vitals_status", "low", "bg"), "#f8d7da", "#ffcdd2"),
    (("vitals_status", "low", "text"), "#842029", "#b71c1c"),
    (("vitals_status", "normal", "bg"), "#d1e7dd", "#dcedc8"),
    (("vitals_status", "normal", "text"), "#0f5132", "#33691e"),
    (("vitals_status", "high", "bg"), "#fff3cd", "#ffe0b2"),
    (("vitals_status", "high", "text"), "#664d03", "#bf360c"),
    (("vitals_status", "neutral", "bg"), "#cfe2ff", "#bbdefb"),
    (("vitals_status", "neutral", "text"), "#084298", "#0d47a1"),
    (("vitals_status", "na", "bg"), "#e2e3e5", "#c5cae9"),
    (("vitals_status", "na", "text"), "#41464b", "#1a237e"),
    (("vitals_chart", "blood_pressure"), "#0d6efd", "#1e88e5"),
    (("vitals_chart", "pulse_rate"), "#fd7e14", "#7cb342"),
    (("vitals_chart", "spo2"), "#198754", "#00897b"),
    (("vitals_chart", "weight"), "#6f42c1", "#3949ab"),
    (("vitals_chart", "hemoglobin"), "#dc3545", "#e53935"),
    (("search", "dropdown_text"), "#212529", "#1f2430"),
    (("search", "result_hover_bg"), "#eef4ff", "#bbdefb"),
    (("search", "tag_bg"), "#edf3ff", "#d1c4e9"),
    (("search", "tag_text"), "#194292", "#4a148c"),
)


def canonical_category_key(name):
    letters_only = re.sub(r"[^A-Z]", "", (name or "").upper())
    if letters_only == "ANC":
        return "ANC"
    if letters_only == "SURGERY":
        return "SURGERY"
    if letters_only in {"MEDICINE", "NONSURGICAL"}:
        return "MEDICINE"
    return None


def update_category_palette_defaults(apps, schema_editor):
    DepartmentConfig = apps.get_model("patients", "DepartmentConfig")
    ThemeSettings = apps.get_model("patients", "ThemeSettings")

    for department in DepartmentConfig.objects.all():
        canonical_key = canonical_category_key(department.name)
        if canonical_key is None:
            continue

        old_defaults = OLD_CATEGORY_THEME_DEFAULTS[canonical_key]
        new_defaults = NEW_CATEGORY_THEME_DEFAULTS[canonical_key]
        bg_color = (department.theme_bg_color or "").strip().lower()
        text_color = (department.theme_text_color or "").strip().lower()

        if bg_color in {"", old_defaults["bg"]} and text_color in {"", old_defaults["text"]}:
            department.theme_bg_color = new_defaults["bg"]
            department.theme_text_color = new_defaults["text"]
            department.save(update_fields=["theme_bg_color", "theme_text_color"])

    for theme_settings in ThemeSettings.objects.all():
        tokens = theme_settings.tokens if isinstance(theme_settings.tokens, dict) else {}
        changed = False

        for path, old_value, new_value in THEME_TOKEN_UPDATES:
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
        ("patients", "0023_case_subcategory"),
    ]

    operations = [
        migrations.RunPython(update_category_palette_defaults, noop_reverse),
    ]
