import re
from copy import deepcopy


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

NEUTRAL_CATEGORY_THEME = {"bg": "#e2e3e5", "text": "#41464b"}

CATEGORY_THEME_DEFAULTS = {
    "ANC": {"bg": "#d1e7dd", "text": "#0f5132"},
    "SURGERY": {"bg": "#fff3cd", "text": "#664d03"},
    "NON SURGICAL": deepcopy(NEUTRAL_CATEGORY_THEME),
}

THEME_DEFAULTS = {
    "shell": {
        "page_bg": "#f8f9fa",
        "page_text": "#212529",
        "surface_bg": "#ffffff",
        "surface_text": "#212529",
        "surface_border": "#dee2e6",
        "muted_text": "#6c757d",
        "link": "#0d6efd",
        "link_hover": "#0a58ca",
        "shadow": "#000000",
    },
    "nav": {
        "bg": "#0d6efd",
        "text": "#ffffff",
        "control_text": "#ffffff",
        "control_border": "#ffffff",
        "control_bg": "#2b6fd1",
        "control_hover_bg": "#3f80db",
        "logout_bg": "#f8f9fa",
        "logout_text": "#000000",
    },
    "case_header": {
        "bg": "#0d6efd",
    },
    "buttons": {
        "primary": {"bg": "#0d6efd", "text": "#ffffff"},
        "secondary": {"bg": "#6c757d", "text": "#ffffff"},
        "warning": {"bg": "#ffc107", "text": "#000000"},
        "danger": {"bg": "#dc3545", "text": "#ffffff"},
        "light": {"bg": "#f8f9fa", "text": "#000000"},
    },
    "alerts": {
        "info": {"bg": "#cff4fc", "text": "#055160"},
        "success": {"bg": "#d1e7dd", "text": "#0a3622"},
        "warning": {"bg": "#fff3cd", "text": "#664d03"},
        "danger": {"bg": "#f8d7da", "text": "#58151c"},
        "light": {"bg": "#fcfcfd", "text": "#495057"},
    },
    "dashboard": {
        "today": {"bg": "#cfe2ff", "text": "#052c65"},
        "upcoming": {"bg": "#cff4fc", "text": "#055160"},
        "overdue": {"bg": "#f8d7da", "text": "#842029"},
    },
    "case_status": {
        "active": {"bg": "#cfe2ff", "text": "#084298"},
        "completed": {"bg": "#d1e7dd", "text": "#0f5132"},
        "cancelled": {"bg": "#f8d7da", "text": "#842029"},
        "loss_to_follow_up": {"bg": "#fff3cd", "text": "#664d03"},
    },
    "task_status": {
        "scheduled": {"bg": "#0d6efd", "text": "#ffffff"},
        "awaiting_reports": {"bg": "#fd7e14", "text": "#ffffff"},
        "completed": {"bg": "#198754", "text": "#ffffff"},
        "cancelled": {"bg": "#6c757d", "text": "#ffffff"},
    },
    "vitals_status": {
        "low": {"bg": "#f8d7da", "text": "#842029"},
        "normal": {"bg": "#d1e7dd", "text": "#0f5132"},
        "high": {"bg": "#fff3cd", "text": "#664d03"},
        "neutral": {"bg": "#cfe2ff", "text": "#084298"},
        "na": {"bg": "#e2e3e5", "text": "#41464b"},
    },
    "vitals_chart": {
        "bp_systolic": "#0d6efd",
        "bp_diastolic": "#6610f2",
        "pulse_rate": "#fd7e14",
        "spo2": "#198754",
        "weight": "#6f42c1",
        "hemoglobin": "#dc3545",
    },
    "search": {
        "dropdown_bg": "#ffffff",
        "dropdown_text": "#212529",
        "result_hover_bg": "#eef4ff",
        "tag_bg": "#edf3ff",
        "tag_text": "#194292",
    },
}

PAIR_GROUPS = (
    ("buttons", "primary"),
    ("buttons", "secondary"),
    ("buttons", "warning"),
    ("buttons", "danger"),
    ("buttons", "light"),
    ("alerts", "info"),
    ("alerts", "success"),
    ("alerts", "warning"),
    ("alerts", "danger"),
    ("alerts", "light"),
    ("dashboard", "today"),
    ("dashboard", "upcoming"),
    ("dashboard", "overdue"),
    ("case_status", "active"),
    ("case_status", "completed"),
    ("case_status", "cancelled"),
    ("case_status", "loss_to_follow_up"),
    ("task_status", "scheduled"),
    ("task_status", "awaiting_reports"),
    ("task_status", "completed"),
    ("task_status", "cancelled"),
    ("vitals_status", "low"),
    ("vitals_status", "normal"),
    ("vitals_status", "high"),
    ("vitals_status", "neutral"),
    ("vitals_status", "na"),
)

CHART_FIELDS = (
    "bp_systolic",
    "bp_diastolic",
    "pulse_rate",
    "spo2",
    "weight",
    "hemoglobin",
)

THEME_FORM_SECTIONS = [
    {
        "title": "Shell, Nav & Case Header",
        "rows": [
            {"label": "Page Background", "fields": [{"name": "shell__page_bg", "label": "Color"}]},
            {"label": "Page Text", "fields": [{"name": "shell__page_text", "label": "Color"}]},
            {"label": "Surface Background", "fields": [{"name": "shell__surface_bg", "label": "Color"}]},
            {"label": "Surface Text", "fields": [{"name": "shell__surface_text", "label": "Color"}]},
            {"label": "Surface Border", "fields": [{"name": "shell__surface_border", "label": "Color"}]},
            {"label": "Muted Text", "fields": [{"name": "shell__muted_text", "label": "Color"}]},
            {"label": "Link", "fields": [{"name": "shell__link", "label": "Color"}]},
            {"label": "Link Hover", "fields": [{"name": "shell__link_hover", "label": "Color"}]},
            {"label": "Shadow", "fields": [{"name": "shell__shadow", "label": "Color"}]},
            {"label": "Nav Background", "fields": [{"name": "nav__bg", "label": "Color"}]},
            {"label": "Nav Text", "fields": [{"name": "nav__text", "label": "Color"}]},
            {"label": "Nav Control Text", "fields": [{"name": "nav__control_text", "label": "Color"}]},
            {"label": "Nav Control Border", "fields": [{"name": "nav__control_border", "label": "Color"}]},
            {"label": "Nav Control Background", "fields": [{"name": "nav__control_bg", "label": "Color"}]},
            {"label": "Nav Control Hover", "fields": [{"name": "nav__control_hover_bg", "label": "Color"}]},
            {"label": "Nav Logout Background", "fields": [{"name": "nav__logout_bg", "label": "Color"}]},
            {"label": "Nav Logout Text", "fields": [{"name": "nav__logout_text", "label": "Color"}]},
            {"label": "Case Header Background", "fields": [{"name": "case_header__bg", "label": "Color"}]},
        ],
    },
    {
        "title": "Buttons & Alerts",
        "rows": [
            {"label": "Primary Button", "fields": [{"name": "buttons__primary__bg", "label": "Background"}, {"name": "buttons__primary__text", "label": "Text"}]},
            {"label": "Secondary Button", "fields": [{"name": "buttons__secondary__bg", "label": "Background"}, {"name": "buttons__secondary__text", "label": "Text"}]},
            {"label": "Warning Button", "fields": [{"name": "buttons__warning__bg", "label": "Background"}, {"name": "buttons__warning__text", "label": "Text"}]},
            {"label": "Danger Button", "fields": [{"name": "buttons__danger__bg", "label": "Background"}, {"name": "buttons__danger__text", "label": "Text"}]},
            {"label": "Light Button", "fields": [{"name": "buttons__light__bg", "label": "Background"}, {"name": "buttons__light__text", "label": "Text"}]},
            {"label": "Info Alert", "fields": [{"name": "alerts__info__bg", "label": "Background"}, {"name": "alerts__info__text", "label": "Text"}]},
            {"label": "Success Alert", "fields": [{"name": "alerts__success__bg", "label": "Background"}, {"name": "alerts__success__text", "label": "Text"}]},
            {"label": "Warning Alert", "fields": [{"name": "alerts__warning__bg", "label": "Background"}, {"name": "alerts__warning__text", "label": "Text"}]},
            {"label": "Danger Alert", "fields": [{"name": "alerts__danger__bg", "label": "Background"}, {"name": "alerts__danger__text", "label": "Text"}]},
            {"label": "Light Alert", "fields": [{"name": "alerts__light__bg", "label": "Background"}, {"name": "alerts__light__text", "label": "Text"}]},
        ],
    },
    {
        "title": "Dashboard",
        "rows": [
            {"label": "Today Card", "fields": [{"name": "dashboard__today__bg", "label": "Background"}, {"name": "dashboard__today__text", "label": "Text"}]},
            {"label": "Upcoming Card", "fields": [{"name": "dashboard__upcoming__bg", "label": "Background"}, {"name": "dashboard__upcoming__text", "label": "Text"}]},
            {"label": "Overdue Card", "fields": [{"name": "dashboard__overdue__bg", "label": "Background"}, {"name": "dashboard__overdue__text", "label": "Text"}]},
        ],
    },
    {
        "title": "Case Status",
        "rows": [
            {"label": "Active", "fields": [{"name": "case_status__active__bg", "label": "Background"}, {"name": "case_status__active__text", "label": "Text"}]},
            {"label": "Completed", "fields": [{"name": "case_status__completed__bg", "label": "Background"}, {"name": "case_status__completed__text", "label": "Text"}]},
            {"label": "Cancelled", "fields": [{"name": "case_status__cancelled__bg", "label": "Background"}, {"name": "case_status__cancelled__text", "label": "Text"}]},
            {"label": "Loss To Follow-up", "fields": [{"name": "case_status__loss_to_follow_up__bg", "label": "Background"}, {"name": "case_status__loss_to_follow_up__text", "label": "Text"}]},
        ],
    },
    {
        "title": "Task Status",
        "rows": [
            {"label": "Scheduled", "fields": [{"name": "task_status__scheduled__bg", "label": "Background"}, {"name": "task_status__scheduled__text", "label": "Text"}]},
            {"label": "Awaiting Reports", "fields": [{"name": "task_status__awaiting_reports__bg", "label": "Background"}, {"name": "task_status__awaiting_reports__text", "label": "Text"}]},
            {"label": "Completed", "fields": [{"name": "task_status__completed__bg", "label": "Background"}, {"name": "task_status__completed__text", "label": "Text"}]},
            {"label": "Cancelled", "fields": [{"name": "task_status__cancelled__bg", "label": "Background"}, {"name": "task_status__cancelled__text", "label": "Text"}]},
        ],
    },
    {
        "title": "Vitals",
        "rows": [
            {"label": "Low Status", "fields": [{"name": "vitals_status__low__bg", "label": "Background"}, {"name": "vitals_status__low__text", "label": "Text"}]},
            {"label": "Normal Status", "fields": [{"name": "vitals_status__normal__bg", "label": "Background"}, {"name": "vitals_status__normal__text", "label": "Text"}]},
            {"label": "High Status", "fields": [{"name": "vitals_status__high__bg", "label": "Background"}, {"name": "vitals_status__high__text", "label": "Text"}]},
            {"label": "Neutral Status", "fields": [{"name": "vitals_status__neutral__bg", "label": "Background"}, {"name": "vitals_status__neutral__text", "label": "Text"}]},
            {"label": "N/A Status", "fields": [{"name": "vitals_status__na__bg", "label": "Background"}, {"name": "vitals_status__na__text", "label": "Text"}]},
            {"label": "BP Systolic Chart", "fields": [{"name": "vitals_chart__bp_systolic", "label": "Color"}]},
            {"label": "BP Diastolic Chart", "fields": [{"name": "vitals_chart__bp_diastolic", "label": "Color"}]},
            {"label": "Pulse Rate Chart", "fields": [{"name": "vitals_chart__pulse_rate", "label": "Color"}]},
            {"label": "SpO2 Chart", "fields": [{"name": "vitals_chart__spo2", "label": "Color"}]},
            {"label": "Weight Chart", "fields": [{"name": "vitals_chart__weight", "label": "Color"}]},
            {"label": "Hemoglobin Chart", "fields": [{"name": "vitals_chart__hemoglobin", "label": "Color"}]},
        ],
    },
    {
        "title": "Search",
        "rows": [
            {"label": "Dropdown Background", "fields": [{"name": "search__dropdown_bg", "label": "Color"}]},
            {"label": "Dropdown Text", "fields": [{"name": "search__dropdown_text", "label": "Color"}]},
            {"label": "Result Hover", "fields": [{"name": "search__result_hover_bg", "label": "Color"}]},
            {"label": "Tag Background", "fields": [{"name": "search__tag_bg", "label": "Color"}]},
            {"label": "Tag Text", "fields": [{"name": "search__tag_text", "label": "Color"}]},
        ],
    },
]


def normalize_hex_color(value):
    if value is None:
        raise ValueError("Color is required.")
    normalized = str(value).strip().lower()
    if not HEX_COLOR_RE.fullmatch(normalized):
        raise ValueError("Enter a valid color in #rrggbb format.")
    return normalized


def hex_to_rgb(hex_color):
    normalized = normalize_hex_color(hex_color)
    return tuple(int(normalized[index : index + 2], 16) for index in (1, 3, 5))


def rgb_to_hex(red, green, blue):
    return f"#{red:02x}{green:02x}{blue:02x}"


def mix_colors(base_color, target_color, ratio):
    base_rgb = hex_to_rgb(base_color)
    target_rgb = hex_to_rgb(target_color)
    mixed = []
    for base_channel, target_channel in zip(base_rgb, target_rgb):
        value = round(base_channel + ((target_channel - base_channel) * ratio))
        mixed.append(max(0, min(255, value)))
    return rgb_to_hex(*mixed)


def rgba_string(hex_color, alpha):
    red, green, blue = hex_to_rgb(hex_color)
    return f"rgba({red}, {green}, {blue}, {alpha})"


def category_lookup_key(name):
    collapsed = re.sub(r"[^A-Z0-9]+", " ", (name or "").upper()).strip()
    return re.sub(r"\s+", " ", collapsed)


def canonical_category_key(name):
    letters_only = re.sub(r"[^A-Z]", "", (name or "").upper())
    if letters_only == "ANC":
        return "ANC"
    if letters_only == "SURGERY":
        return "SURGERY"
    if letters_only == "NONSURGICAL":
        return "NON SURGICAL"
    return None


def get_default_category_theme(name):
    canonical_key = canonical_category_key(name)
    default_theme = CATEGORY_THEME_DEFAULTS.get(canonical_key, NEUTRAL_CATEGORY_THEME)
    return {"bg": default_theme["bg"], "text": default_theme["text"]}


def _merge_nested(base, override):
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_nested(base[key], value)
            continue
        if isinstance(value, str):
            try:
                base[key] = normalize_hex_color(value)
            except ValueError:
                continue


def add_theme_derivatives(tokens):
    resolved = deepcopy(tokens)
    resolved["shell"]["shadow_rgba"] = rgba_string(resolved["shell"]["shadow"], 0.12)
    resolved["shell"]["surface_hover_bg"] = mix_colors(
        resolved["shell"]["surface_bg"],
        resolved["shell"]["surface_text"],
        0.10,
    )
    resolved["shell"]["page_focus_shadow"] = rgba_string(resolved["shell"]["link"], 0.25)
    resolved["search"]["dropdown_border"] = mix_colors(
        resolved["search"]["dropdown_bg"],
        resolved["search"]["dropdown_text"],
        0.20,
    )
    resolved["search"]["tag_border"] = mix_colors(
        resolved["search"]["tag_bg"],
        resolved["search"]["tag_text"],
        0.20,
    )

    for section_name, token_name in PAIR_GROUPS:
        pair = resolved[section_name][token_name]
        pair["border"] = mix_colors(pair["bg"], pair["text"], 0.20)
        pair["hover_bg"] = mix_colors(pair["bg"], pair["text"], 0.10)
        pair["focus_shadow"] = rgba_string(pair["bg"], 0.25)

    for chart_name in CHART_FIELDS:
        chart_color = resolved["vitals_chart"][chart_name]
        resolved["vitals_chart"][f"{chart_name}_fill"] = rgba_string(chart_color, 0.18)
    return resolved


def merge_theme_tokens(saved_tokens):
    merged = deepcopy(THEME_DEFAULTS)
    _merge_nested(merged, saved_tokens or {})
    return add_theme_derivatives(merged)


def build_theme_css_vars(theme_tokens):
    variables = {
        "--theme-shell-page-bg": theme_tokens["shell"]["page_bg"],
        "--theme-shell-page-text": theme_tokens["shell"]["page_text"],
        "--theme-shell-surface-bg": theme_tokens["shell"]["surface_bg"],
        "--theme-shell-surface-text": theme_tokens["shell"]["surface_text"],
        "--theme-shell-surface-border": theme_tokens["shell"]["surface_border"],
        "--theme-shell-muted-text": theme_tokens["shell"]["muted_text"],
        "--theme-shell-link": theme_tokens["shell"]["link"],
        "--theme-shell-link-hover": theme_tokens["shell"]["link_hover"],
        "--theme-shell-shadow-color": theme_tokens["shell"]["shadow"],
        "--theme-shell-shadow": theme_tokens["shell"]["shadow_rgba"],
        "--theme-shell-surface-hover-bg": theme_tokens["shell"]["surface_hover_bg"],
        "--theme-shell-focus-shadow": theme_tokens["shell"]["page_focus_shadow"],
        "--theme-nav-bg": theme_tokens["nav"]["bg"],
        "--theme-nav-text": theme_tokens["nav"]["text"],
        "--theme-nav-control-text": theme_tokens["nav"]["control_text"],
        "--theme-nav-control-border": theme_tokens["nav"]["control_border"],
        "--theme-nav-control-bg": theme_tokens["nav"]["control_bg"],
        "--theme-nav-control-hover-bg": theme_tokens["nav"]["control_hover_bg"],
        "--theme-nav-logout-bg": theme_tokens["nav"]["logout_bg"],
        "--theme-nav-logout-text": theme_tokens["nav"]["logout_text"],
        "--theme-case-header-bg": theme_tokens["case_header"]["bg"],
        "--theme-search-dropdown-bg": theme_tokens["search"]["dropdown_bg"],
        "--theme-search-dropdown-text": theme_tokens["search"]["dropdown_text"],
        "--theme-search-dropdown-border": theme_tokens["search"]["dropdown_border"],
        "--theme-search-result-hover-bg": theme_tokens["search"]["result_hover_bg"],
        "--theme-search-tag-bg": theme_tokens["search"]["tag_bg"],
        "--theme-search-tag-text": theme_tokens["search"]["tag_text"],
        "--theme-search-tag-border": theme_tokens["search"]["tag_border"],
    }

    for section_name, token_name in PAIR_GROUPS:
        pair = theme_tokens[section_name][token_name]
        prefix = f"--theme-{section_name.replace('_', '-')}-{token_name.replace('_', '-')}"
        variables[f"{prefix}-bg"] = pair["bg"]
        variables[f"{prefix}-text"] = pair["text"]
        variables[f"{prefix}-border"] = pair["border"]
        variables[f"{prefix}-hover-bg"] = pair["hover_bg"]
        variables[f"{prefix}-focus-shadow"] = pair["focus_shadow"]

    for chart_name in CHART_FIELDS:
        prefix = f"--theme-vitals-chart-{chart_name.replace('_', '-')}"
        variables[prefix] = theme_tokens["vitals_chart"][chart_name]
        variables[f"{prefix}-fill"] = theme_tokens["vitals_chart"][f"{chart_name}_fill"]
    return variables


def build_theme_category_colors(categories):
    default_theme = {
        "bg": NEUTRAL_CATEGORY_THEME["bg"],
        "text": NEUTRAL_CATEGORY_THEME["text"],
        "border": mix_colors(NEUTRAL_CATEGORY_THEME["bg"], NEUTRAL_CATEGORY_THEME["text"], 0.20),
        "hover_bg": mix_colors(NEUTRAL_CATEGORY_THEME["bg"], NEUTRAL_CATEGORY_THEME["text"], 0.10),
    }
    theme_map = {
        "by_id": {},
        "by_lookup": {},
        "canonical": {},
        "default": default_theme,
    }
    for category in categories:
        category_defaults = get_default_category_theme(category.name)
        bg_color = normalize_hex_color(getattr(category, "theme_bg_color", "") or category_defaults["bg"])
        text_color = normalize_hex_color(getattr(category, "theme_text_color", "") or category_defaults["text"])
        color_pair = {
            "name": category.name,
            "bg": bg_color,
            "text": text_color,
            "border": mix_colors(bg_color, text_color, 0.20),
            "hover_bg": mix_colors(bg_color, text_color, 0.10),
        }
        if getattr(category, "id", None) is not None:
            theme_map["by_id"][category.id] = color_pair
        theme_map["by_lookup"][category_lookup_key(category.name)] = color_pair
        canonical_key = canonical_category_key(category.name)
        if canonical_key and canonical_key not in theme_map["canonical"]:
            theme_map["canonical"][canonical_key] = color_pair
    return theme_map


def resolve_category_theme(theme_category_colors, category_value):
    if isinstance(category_value, str):
        return (
            theme_category_colors["by_lookup"].get(category_lookup_key(category_value))
            or theme_category_colors["canonical"].get(canonical_category_key(category_value))
            or theme_category_colors["default"]
        )

    category_id = getattr(category_value, "id", None)
    if category_id in theme_category_colors["by_id"]:
        return theme_category_colors["by_id"][category_id]

    category_name = getattr(category_value, "name", "")
    return (
        theme_category_colors["by_lookup"].get(category_lookup_key(category_name))
        or theme_category_colors["canonical"].get(canonical_category_key(category_name))
        or theme_category_colors["default"]
    )


def theme_field_definitions():
    definitions = []
    for section in THEME_FORM_SECTIONS:
        for row in section["rows"]:
            for field in row["fields"]:
                definitions.append(field["name"])
    return definitions


def flatten_theme_tokens(theme_tokens):
    flat = {}
    for field_name in theme_field_definitions():
        current = theme_tokens
        for part in field_name.split("__"):
            current = current[part]
        flat[field_name] = current
    return flat


def unflatten_theme_tokens(flat_values):
    nested = {}
    for field_name in theme_field_definitions():
        value = flat_values[field_name]
        current = nested
        parts = field_name.split("__")
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return nested


def normalize_theme_tokens(saved_tokens):
    return unflatten_theme_tokens(flatten_theme_tokens(merge_theme_tokens(saved_tokens)))


def field_name_to_css_var(field_name):
    if field_name == "shell__shadow":
        return "--theme-shell-shadow-color"
    return f"--theme-{field_name.replace('__', '-').replace('_', '-')}"
