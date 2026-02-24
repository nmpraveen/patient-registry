from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class CaseStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    LOSS_TO_FOLLOW_UP = "LOSS_TO_FOLLOW_UP", "Loss to Follow-up"


class TaskStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    AWAITING_REPORTS = "AWAITING_REPORTS", "Awaiting Reports"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class TaskType(models.TextChoices):
    VISIT = "VISIT", "Visit"
    LAB = "LAB", "Lab"
    PROCEDURE = "PROCEDURE", "Procedure"
    CALL = "CALL", "Call"
    CUSTOM = "CUSTOM", "Custom"


class DepartmentConfig(models.Model):
    name = models.CharField(max_length=100, unique=True)
    auto_follow_up_days = models.PositiveIntegerField(default=30)
    predefined_actions = models.JSONField(default=list, blank=True)
    metadata_template = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Case(models.Model):
    uhid = models.CharField(max_length=64, unique=True)
    patient_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=10, db_index=True)
    category = models.ForeignKey(DepartmentConfig, on_delete=models.PROTECT, related_name="cases")
    status = models.CharField(max_length=32, choices=CaseStatus.choices, default=CaseStatus.ACTIVE)
    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_cases")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["patient_name"]), models.Index(fields=["uhid"]), models.Index(fields=["phone_number"])]

    def clean(self):
        if self.phone_number and (not self.phone_number.isdigit() or len(self.phone_number) != 10):
            raise ValidationError({"phone_number": "Phone number must be exactly 10 digits."})

        if self.status == CaseStatus.ACTIVE:
            duplicate_qs = Case.objects.filter(uhid=self.uhid, status=CaseStatus.ACTIVE)
            if self.pk:
                duplicate_qs = duplicate_qs.exclude(pk=self.pk)
            if duplicate_qs.exists():
                raise ValidationError({"uhid": "No duplicate active cases are allowed for the same UHID."})

    def __str__(self) -> str:
        return f"{self.uhid} - {self.patient_name}"


class Task(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    due_date = models.DateField()
    status = models.CharField(max_length=32, choices=TaskStatus.choices, default=TaskStatus.SCHEDULED)
    assigned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks")
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.CUSTOM)
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_tasks")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "id"]

    def save(self, *args, **kwargs):
        if self.status == TaskStatus.COMPLETED and self.completed_at is None:
            self.completed_at = timezone.now()
        if self.status != TaskStatus.COMPLETED:
            self.completed_at = None
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.case.uhid}: {self.title}"


class CaseActivityLog(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="activity_logs")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.case.uhid} @ {self.created_at:%Y-%m-%d %H:%M}"
