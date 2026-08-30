import re
from copy import deepcopy


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

NEUTRAL_CATEGORY_THEME = {"bg": "#e2e3e5", "text": "#41464b"}

CATEGORY_THEME_DEFAULTS = {
    "ANC": {"bg": "#ffe0b2", "text": "#b8320a"},
    "SURGERY": {"bg": "#b2dfdb", "text": "#004d40"},
    "MEDICINE": {"bg": "#c5cae9", "text": "#1a237e"},
}

THEME_DEFAULTS = {
    "shell": {
        "page_bg": "#f7f4ef",
        "page_text": "#1f2430",
        "surface_bg": "#ffffff",
        "surface_text": "#1f2430",
        "surface_border": "#e5dfd4",
        "muted_text": "#6d6a63",
        "link": "#0b5cad",
        "link_hover": "#0d47a1",
        "focus_indicator": "#0b5cad",
        "shadow": "#1a237e",
    },
    "nav": {
        "bg": "#fffdf8",
        "text": "#1e3a5f",
        "control_text": "#646c7a",
        "control_border": "#dfe4ea",
        "control_bg": "#f3f5f7",
        "control_hover_bg": "#e9edf2",
        "logout_bg": "#f3f5f7",
        "logout_text": "#656d7b",
    },
    "case_header": {
        "bg": "#3949ab",
    },
    "buttons": {
        "primary": {"bg": "#64b5f6", "text": "#073763", "outline_text": "#0b5cad"},
        "success": {"bg": "#80cbc4", "text": "#004d40", "outline_text": "#00695c"},
        "secondary": {"bg": "#b39ddb", "text": "#4a148c", "outline_text": "#4a148c"},
        "warning": {"bg": "#ffab91", "text": "#7f1d1d", "outline_text": "#8a2c0b"},
        "danger": {"bg": "#ef9a9a", "text": "#7f1d1d", "outline_text": "#8b1e1e"},
        "light": {"bg": "#f7f4ef", "text": "#1a237e", "outline_text": "#1a237e"},
    },
    "alerts": {
        "info": {"bg": "#bbdefb", "text": "#0d47a1"},
        "success": {"bg": "#dcedc8", "text": "#33691e"},
        "warning": {"bg": "#ffe0b2", "text": "#b8320a"},
        "danger": {"bg": "#ffcdd2", "text": "#b71c1c"},
        "light": {"bg": "#f7f4ef", "text": "#5f5a52"},
    },
    "dashboard": {
        "today": {"bg": "#dcedc8", "text": "#33691e"},
        "recent": {"bg": "#d1c4e9", "text": "#4a148c"},
        "upcoming": {"bg": "#bbdefb", "text": "#0d47a1"},
        "overdue": {"bg": "#ffcdd2", "text": "#b71c1c"},
    },
    "case_status": {
        "active": {"bg": "#bbdefb", "text": "#0d47a1"},
        "completed": {"bg": "#dcedc8", "text": "#33691e"},
        "cancelled": {"bg": "#ffcdd2", "text": "#b71c1c"},
        "loss_to_follow_up": {"bg": "#d1c4e9", "text": "#4a148c"},
    },
    "task_status": {
        "scheduled": {"bg": "#bbdefb", "text": "#0d47a1"},
        "awaiting_reports": {"bg": "#ffe0b2", "text": "#b8320a"},
        "completed": {"bg": "#dcedc8", "text": "#33691e"},
        "cancelled": {"bg": "#ffcdd2", "text": "#b71c1c"},
    },
    "vitals_status": {
        "low": {"bg": "#ffcdd2", "text": "#b71c1c"},
        "normal": {"bg": "#dcedc8", "text": "#33691e"},
        "high": {"bg": "#ffe0b2", "text": "#b8320a"},
        "neutral": {"bg": "#bbdefb", "text": "#0d47a1"},
        "na": {"bg": "#c5cae9", "text": "#1a237e"},
    },
    "vitals_chart": {
        "blood_pressure": "#1e88e5",
        "pulse_rate": "#7cb342",
        "spo2": "#00897b",
        "weight": "#3949ab",
        "hemoglobin": "#e53935",
    },
    "search": {
        "dropdown_bg": "#ffffff",
        "dropdown_text": "#1f2430",
        "result_hover_bg": "#bbdefb",
        "tag_bg": "#d1c4e9",
        "tag_text": "#4a148c",
        "gender_female": {"bg": "#fdf0ec", "text": "#9c3f3f"},
        "gender_male": {"bg": "#e8f0f7", "text": "#315f86"},
        "gender_other": {"bg": "#f5f0ea", "text": "#655c55"},
    },
}

PAIR_GROUPS = (
    ("buttons", "primary"),
    ("buttons", "success"),
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
    ("dashboard", "recent"),
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
    ("search", "gender_female"),
    ("search", "gender_male"),
    ("search", "gender_other"),
)

BUTTON_OUTLINE_GROUPS = ("primary", "success", "secondary", "warning", "danger", "light")

THEME_CONTRAST_RULES = (
    ("shell__page_text", "shell__page_bg", 4.5, "Page text"),
    ("shell__surface_text", "shell__surface_bg", 4.5, "Surface text"),
    ("shell__muted_text", "shell__page_bg", 4.5, "Muted text on page"),
    ("shell__muted_text", "shell__surface_bg", 4.5, "Muted text on surfaces"),
    ("shell__link", "shell__page_bg", 4.5, "Page link text"),
    ("shell__link", "shell__surface_bg", 4.5, "Surface link text"),
    ("shell__link_hover", "shell__page_bg", 4.5, "Page link hover text"),
    ("shell__link_hover", "shell__surface_bg", 4.5, "Surface link hover text"),
    ("nav__text", "nav__bg", 4.5, "Navigation text"),
    ("nav__control_text", "nav__control_bg", 4.5, "Navigation control text"),
    ("nav__control_text", "nav__control_hover_bg", 4.5, "Navigation control hover text"),
    ("nav__text", "nav__control_hover_bg", 4.5, "Navigation icon hover text"),
    ("nav__logout_text", "nav__logout_bg", 4.5, "Logout control text"),
    ("shell__surface_bg", "case_header__bg", 4.5, "New case action text"),
    ("search__dropdown_text", "search__dropdown_bg", 4.5, "Search result text"),
    ("search__dropdown_text", "search__result_hover_bg", 4.5, "Selected search result text"),
    ("search__tag_text", "search__tag_bg", 4.5, "Search tag text"),
) + tuple(
    (
        f"{section_name}__{token_name}__text",
        f"{section_name}__{token_name}__bg",
        4.5,
        f"{section_name.replace('_', ' ').title()} {token_name.replace('_', ' ').title()}",
    )
    for section_name, token_name in PAIR_GROUPS
 ) + tuple(
    (
        f"buttons__{token_name}__outline_text",
        background_field,
        4.5,
        f"{token_name.replace('_', ' ').title()} outline button text on {surface_name}",
    )
    for token_name in BUTTON_OUTLINE_GROUPS
    for background_field, surface_name in (
        ("shell__page_bg", "page"),
        ("shell__surface_bg", "surface"),
    )
)

THEME_DERIVED_TEXT_CONTRAST_RULES = tuple(
    (
        f"{section_name}__{token_name}__text",
        f"{section_name}__{token_name}__bg",
        0.10,
        4.5,
        f"{section_name.replace('_', ' ').title()} {token_name.replace('_', ' ').title()} hover/active",
    )
    for section_name, token_name in PAIR_GROUPS
)

THEME_MIXED_TEXT_CONTRAST_RULES = (
    (
        "shell__surface_bg",
        "case_header__bg",
        "shell__page_text",
        0.12,
        4.5,
        "New case action hover text",
    ),
)

THEME_FOCUS_CONTRAST_RULES = (
    ("shell__focus_indicator", "shell__page_bg", 3.0, "Page focus indicator"),
    ("shell__focus_indicator", "shell__surface_bg", 3.0, "Surface focus indicator"),
    ("shell__focus_indicator", "nav__bg", 3.0, "Navigation focus indicator"),
)

CHART_FIELDS = (
    "blood_pressure",
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
            {"label": "Focus Indicator", "fields": [{"name": "shell__focus_indicator", "label": "Color"}]},
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
            {"label": "Primary Button", "fields": [{"name": "buttons__primary__bg", "label": "Background"}, {"name": "buttons__primary__text", "label": "Text"}, {"name": "buttons__primary__outline_text", "label": "Outline Text"}]},
            {"label": "Success Button", "fields": [{"name": "buttons__success__bg", "label": "Background"}, {"name": "buttons__success__text", "label": "Text"}, {"name": "buttons__success__outline_text", "label": "Outline Text"}]},
            {"label": "Secondary Button", "fields": [{"name": "buttons__secondary__bg", "label": "Background"}, {"name": "buttons__secondary__text", "label": "Text"}, {"name": "buttons__secondary__outline_text", "label": "Outline Text"}]},
            {"label": "Warning Button", "fields": [{"name": "buttons__warning__bg", "label": "Background"}, {"name": "buttons__warning__text", "label": "Text"}, {"name": "buttons__warning__outline_text", "label": "Outline Text"}]},
            {"label": "Danger Button", "fields": [{"name": "buttons__danger__bg", "label": "Background"}, {"name": "buttons__danger__text", "label": "Text"}, {"name": "buttons__danger__outline_text", "label": "Outline Text"}]},
            {"label": "Light Button", "fields": [{"name": "buttons__light__bg", "label": "Background"}, {"name": "buttons__light__text", "label": "Text"}, {"name": "buttons__light__outline_text", "label": "Outline Text"}]},
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
            {"label": "Recently Added Card", "fields": [{"name": "dashboard__recent__bg", "label": "Background"}, {"name": "dashboard__recent__text", "label": "Text"}]},
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
            {"label": "Blood Pressure Chart", "fields": [{"name": "vitals_chart__blood_pressure", "label": "Color"}]},
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
            {
                "label": "Female Tag",
                "fields": [
                    {"name": "search__gender_female__bg", "label": "Background"},
                    {"name": "search__gender_female__text", "label": "Text"},
                ],
            },
            {
                "label": "Male Tag",
                "fields": [
                    {"name": "search__gender_male__bg", "label": "Background"},
                    {"name": "search__gender_male__text", "label": "Text"},
                ],
            },
            {
                "label": "Other Tag",
                "fields": [
                    {"name": "search__gender_other__bg", "label": "Background"},
                    {"name": "search__gender_other__text", "label": "Text"},
                ],
            },
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


def contrast_ratio(first_color, second_color):
    def relative_luminance(hex_color):
        channels = []
        for channel in hex_to_rgb(hex_color):
            normalized = channel / 255
            channels.append(
                normalized / 12.92
                if normalized <= 0.04045
                else ((normalized + 0.055) / 1.055) ** 2.4
            )
        return (0.2126 * channels[0]) + (0.7152 * channels[1]) + (0.0722 * channels[2])

    first_luminance = relative_luminance(first_color)
    second_luminance = relative_luminance(second_color)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


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


def contrast_safe_hover_color(background_color, text_color, ratio=0.10):
    """Derive an interaction background that increases text contrast."""
    lighter_hover = mix_colors(background_color, "#ffffff", ratio)
    darker_hover = mix_colors(background_color, "#000000", ratio)
    return max(
        (lighter_hover, darker_hover),
        key=lambda color: contrast_ratio(text_color, color),
    )


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
    if letters_only in {"MEDICINE", "NONSURGICAL"}:
        return "MEDICINE"
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


def _normalize_vitals_chart_tokens(resolved):
    chart_tokens = resolved.setdefault("vitals_chart", {})
    chart_tokens.setdefault("blood_pressure", THEME_DEFAULTS["vitals_chart"]["blood_pressure"])
    chart_tokens.pop("bp_systolic", None)
    chart_tokens.pop("bp_diastolic", None)


def _normalize_theme_overrides(saved_tokens):
    normalized = deepcopy(saved_tokens or {})
    chart_tokens = normalized.get("vitals_chart")
    if isinstance(chart_tokens, dict) and "blood_pressure" not in chart_tokens:
        legacy_color = chart_tokens.get("bp_systolic") or chart_tokens.get("bp_diastolic")
        if legacy_color:
            chart_tokens["blood_pressure"] = legacy_color
    return normalized


def add_theme_derivatives(tokens):
    resolved = deepcopy(tokens)
    _normalize_vitals_chart_tokens(resolved)
    resolved["shell"]["shadow_rgba"] = rgba_string(resolved["shell"]["shadow"], 0.12)
    resolved["shell"]["surface_hover_bg"] = mix_colors(
        resolved["shell"]["surface_bg"],
        resolved["shell"]["surface_text"],
        0.10,
    )
    resolved["shell"]["page_focus_shadow"] = rgba_string(resolved["shell"]["focus_indicator"], 0.25)
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
        pair["hover_bg"] = contrast_safe_hover_color(pair["bg"], pair["text"], 0.10)
        pair["focus_shadow"] = rgba_string(pair["bg"], 0.25)

    for chart_name in CHART_FIELDS:
        chart_color = resolved["vitals_chart"][chart_name]
        resolved["vitals_chart"][f"{chart_name}_fill"] = rgba_string(chart_color, 0.18)
    return resolved


def merge_theme_tokens(saved_tokens):
    merged = deepcopy(THEME_DEFAULTS)
    _merge_nested(merged, _normalize_theme_overrides(saved_tokens))
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
        "--theme-shell-focus-indicator": theme_tokens["shell"]["focus_indicator"],
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
        if section_name == "buttons":
            variables[f"{prefix}-outline-text"] = pair["outline_text"]
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
        "hover_bg": contrast_safe_hover_color(
            NEUTRAL_CATEGORY_THEME["bg"], NEUTRAL_CATEGORY_THEME["text"], 0.10
        ),
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
            "hover_bg": contrast_safe_hover_color(bg_color, text_color, 0.10),
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
