from datetime import timedelta

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


class SurgicalPathway(models.TextChoices):
    PLANNED_SURGERY = "PLANNED_SURGERY", "Planned for surgery"
    SURVEILLANCE = "SURVEILLANCE", "Surveillance only"


class ReviewFrequency(models.TextChoices):
    MONTHLY = "MONTHLY", "Monthly"
    QUARTERLY = "QUARTERLY", "Every 3 months"
    HALF_YEARLY = "HALF_YEARLY", "Every 6 months"
    YEARLY = "YEARLY", "Yearly"


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

    lmp = models.DateField(blank=True, null=True)
    edd = models.DateField(blank=True, null=True)
    surgical_pathway = models.CharField(max_length=32, choices=SurgicalPathway.choices, blank=True)
    surgery_done = models.BooleanField(default=False)
    review_frequency = models.CharField(max_length=20, choices=ReviewFrequency.choices, blank=True)
    review_date = models.DateField(blank=True, null=True)
    surgery_date = models.DateField(blank=True, null=True)

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

        category_name = self.category.name.upper() if self.category_id else ""
        if category_name == "ANC":
            if not self.lmp or not self.edd:
                raise ValidationError("ANC cases require both LMP and EDD.")
        if category_name == "SURGERY":
            if not self.surgical_pathway:
                raise ValidationError({"surgical_pathway": "Please choose surveillance or planned surgery."})
            if self.surgical_pathway == SurgicalPathway.SURVEILLANCE and not self.review_date:
                raise ValidationError({"review_date": "Surveillance cases require a review date."})
            if self.surgical_pathway == SurgicalPathway.PLANNED_SURGERY and not self.surgery_date:
                raise ValidationError({"surgery_date": "Planned surgery cases require a surgery date."})
        if category_name in ["NON_SURGICAL", "NONSURGICAL"] and not self.review_date:
            raise ValidationError({"review_date": "Non-surgical cases require a review date."})

    @property
    def trimester(self):
        if not self.lmp:
            return None
        days = (timezone.localdate() - self.lmp).days
        weeks = max(days // 7, 0)
        if weeks < 13:
            return "First"
        if weeks < 28:
            return "Second"
        return "Third"

    def __str__(self) -> str:
        return f"{self.uhid} - {self.patient_name}"


class Task(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    due_date = models.DateField()
    status = models.CharField(max_length=32, choices=TaskStatus.choices, default=TaskStatus.SCHEDULED)
    assigned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks")
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.CUSTOM)
    frequency_label = models.CharField(max_length=40, blank=True)
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


def frequency_to_days(freq: str) -> int:
    return {
        ReviewFrequency.MONTHLY: 30,
        ReviewFrequency.QUARTERLY: 90,
        ReviewFrequency.HALF_YEARLY: 180,
        ReviewFrequency.YEARLY: 365,
    }.get(freq, 30)


def build_default_tasks(case: Case, actor):
    category_name = case.category.name.upper()
    tasks = []
    today = timezone.localdate()

    if category_name == "ANC":
        anc_dates = [today, today + timedelta(days=30), today + timedelta(days=60)]
        titles = ["ANC Visit", "USG Review", "BP & Labs"]
        for title, due in zip(titles, anc_dates):
            if case.edd and due > case.edd:
                due = case.edd
            tasks.append((title, due, TaskType.VISIT, "ANC protocol"))
    elif category_name == "SURGERY":
        if case.surgical_pathway == SurgicalPathway.PLANNED_SURGERY:
            base_date = case.surgery_date or today
            tasks.extend(
                [
                    ("Lab test", base_date - timedelta(days=7), TaskType.LAB, "Pre-op"),
                    ("Xray", base_date - timedelta(days=7), TaskType.PROCEDURE, "Pre-op"),
                    ("ECG", base_date - timedelta(days=7), TaskType.PROCEDURE, "Pre-op"),
                    ("Inform Anesthetist", base_date - timedelta(days=5), TaskType.CALL, "Pre-op"),
                    ("Surgery Date", base_date, TaskType.PROCEDURE, "Planned surgery"),
                ]
            )
        else:
            review = case.review_date or today + timedelta(days=30)
            tasks.append(("Surveillance Review", review, TaskType.VISIT, case.get_review_frequency_display() or "Review"))
    else:
        review = case.review_date or today + timedelta(days=30)
        action = (case.category.predefined_actions[0] if case.category.predefined_actions else "Review by consultant")
        tasks.append((action, review, TaskType.CUSTOM, case.get_review_frequency_display() or "Review"))

    created = []
    for title, due_date, task_type, frequency_label in tasks:
        task = Task.objects.create(
            case=case,
            title=title,
            due_date=due_date,
            task_type=task_type,
            frequency_label=frequency_label,
            created_by=actor,
        )
        created.append(task)

    return created
