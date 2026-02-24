from django.contrib import admin

from .models import Case, CaseActivityLog, DepartmentConfig, RoleSetting, Task


@admin.register(DepartmentConfig)
class DepartmentConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "auto_follow_up_days")
    search_fields = ("name",)


@admin.register(RoleSetting)
class RoleSettingAdmin(admin.ModelAdmin):
    list_display = (
        "role_name",
        "can_case_create",
        "can_case_edit",
        "can_task_create",
        "can_task_edit",
        "can_note_add",
        "can_manage_settings",
    )


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("id", "uhid", "first_name", "last_name", "phone_number", "category", "status", "review_date", "updated_at")
    search_fields = ("uhid", "first_name", "last_name", "patient_name", "phone_number")
    list_filter = ("status", "category", "surgical_pathway")
    inlines = [TaskInline]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "title", "due_date", "status", "assigned_user", "task_type", "frequency_label")
    search_fields = ("title", "case__uhid", "case__first_name", "case__last_name")
    list_filter = ("status", "task_type", "due_date")


@admin.register(CaseActivityLog)
class CaseActivityLogAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "task", "user", "created_at")
    search_fields = ("case__uhid", "note", "task__title")
