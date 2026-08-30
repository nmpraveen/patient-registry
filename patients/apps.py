from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "patients"

    def ready(self):
        from .audit import install_user_audit_boundary

        install_user_audit_boundary()
        from . import signals  # noqa: F401
