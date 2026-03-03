from pathlib import Path

from django.conf import settings
from django.utils import timezone


VERSION_FILE = Path(settings.BASE_DIR) / "VERSION"


def app_version(request):
    if VERSION_FILE.exists():
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    else:
        version = timezone.now().strftime("%Y.%m.%d.%H.%M")

    return {"app_version": version}
