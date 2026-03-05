from django import template
from django.utils.safestring import mark_safe

from patients.theme import build_theme_css_vars, resolve_category_theme


register = template.Library()


@register.simple_tag
def theme_css_vars(theme_tokens):
    declarations = [f"{name}: {value};" for name, value in build_theme_css_vars(theme_tokens).items()]
    return mark_safe("\n".join(declarations))


@register.simple_tag
def category_theme_style(category, theme_category_colors):
    theme = resolve_category_theme(theme_category_colors, category)
    return mark_safe(
        f"--theme-category-bg: {theme['bg']}; "
        f"--theme-category-text: {theme['text']}; "
        f"--theme-category-border: {theme['border']}; "
        f"--theme-category-hover-bg: {theme['hover_bg']};"
    )


@register.filter
def message_alert_class(tags):
    tag_set = set((tags or "").split())
    if "error" in tag_set:
        return "danger"
    if "warning" in tag_set:
        return "warning"
    if "success" in tag_set:
        return "success"
    if "info" in tag_set:
        return "info"
    if "debug" in tag_set:
        return "light"
    return "info"
