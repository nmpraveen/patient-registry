from django.contrib import admin

from .models import Case, CaseActivityLog, DepartmentConfig, Task


@admin.register(DepartmentConfig)
class DepartmentConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "auto_follow_up_days")
    search_fields = ("name",)


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("id", "uhid", "patient_name", "phone_number", "category", "status", "updated_at")
    search_fields = ("uhid", "patient_name", "phone_number")
    list_filter = ("status", "category")
    inlines = [TaskInline]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "title", "due_date", "status", "assigned_user", "task_type")
    search_fields = ("title", "case__uhid", "case__patient_name")
    list_filter = ("status", "task_type", "due_date")


@admin.register(CaseActivityLog)
class CaseActivityLogAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "task", "user", "created_at")
    search_fields = ("case__uhid", "note", "task__title")
