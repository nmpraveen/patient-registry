from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "patients"

    def ready(self):
        from .backup_scheduler import start_background_scheduler

        start_background_scheduler()
