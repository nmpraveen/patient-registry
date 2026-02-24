from django.contrib import admin

from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "last_name", "phone", "email", "created_at")
    search_fields = ("first_name", "last_name", "phone", "email")
    list_filter = ("sex", "created_at")
    ordering = ("last_name", "first_name")
