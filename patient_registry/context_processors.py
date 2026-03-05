from pathlib import Path

from django.conf import settings
from django.utils import timezone

from patients.models import DepartmentConfig, ThemeSettings
from patients.theme import build_theme_category_colors, merge_theme_tokens


VERSION_FILE = Path(settings.BASE_DIR) / "VERSION"


def app_version(request):
    if VERSION_FILE.exists():
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    else:
        version = timezone.now().strftime("%Y.%m.%d.%H.%M")

    return {"app_version": version}


def global_theme(request):
    theme_tokens = merge_theme_tokens(ThemeSettings.objects.filter(pk=1).values_list("tokens", flat=True).first() or {})
    theme_categories = DepartmentConfig.objects.only("id", "name", "theme_bg_color", "theme_text_color")
    return {
        "theme_tokens": theme_tokens,
        "theme_category_colors": build_theme_category_colors(theme_categories),
    }
