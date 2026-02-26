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


class CallOutcome(models.TextChoices):
    ANSWERED_CONFIRMED_VISIT = "ANSWERED_CONFIRMED_VISIT", "Answered - Confirmed visit"
    ANSWERED_UNCERTAIN = "ANSWERED_UNCERTAIN", "Answered - Uncertain"
    NO_ANSWER = "NO_ANSWER", "No answer"
    SWITCHED_OFF = "SWITCHED_OFF", "Switched off"
    CALL_REJECTED = "CALL_REJECTED", "Call rejected"
    INVALID_NUMBER = "INVALID_NUMBER", "Invalid number"
    PATIENT_SHIFTED = "PATIENT_SHIFTED", "Patient shifted"
    PATIENT_DECLINED = "PATIENT_DECLINED", "Patient declined"
    RUDE_BEHAVIOR = "RUDE_BEHAVIOR", "Rude behavior"
    CALL_BACK_LATER = "CALL_BACK_LATER", "Call back later"


class CallCommunicationStatus(models.TextChoices):
    NONE = "NONE", "Not contacted"
    CONFIRMED = "CONFIRMED", "Confirmed"
    NOT_REACHABLE = "NOT_REACHABLE", "Not reachable"
    INVALID_CONTACT = "INVALID_CONTACT", "Invalid contact"
    LOST = "LOST", "Lost follow-up"
    CALL_BACK_LATER = "CALL_BACK_LATER", "Call back later"


class SurgicalPathway(models.TextChoices):
    PLANNED_SURGERY = "PLANNED_SURGERY", "Planned for surgery"
    SURVEILLANCE = "SURVEILLANCE", "Surveillance only"


class ReviewFrequency(models.TextChoices):
    MONTHLY = "MONTHLY", "Monthly"
    QUARTERLY = "QUARTERLY", "Every 3 months"
    HALF_YEARLY = "HALF_YEARLY", "Every 6 months"
    YEARLY = "YEARLY", "Yearly"


class Gender(models.TextChoices):
    FEMALE = "FEMALE", "Female"
    MALE = "MALE", "Male"
    OTHER = "OTHER", "Other"
    UNKNOWN = "UNKNOWN", "Unknown"


class NonCommunicableDisease(models.TextChoices):
    T2DM = "T2DM", "T2DM"
    SHTN = "SHTN", "SHTN"
    BA = "BA", "BA"
    EPILEPSY = "EPILEPSY", "Epilepsy"
    CAD = "CAD", "CAD"
    CKD = "CKD", "CKD"
    CLD = "CLD", "CLD"
    CVA = "CVA", "CVA"
    COPD = "COPD", "COPD"
    THYROID = "THYROID", "Thyroid"
    SMOKING = "SMOKING", "Smoking"
    ALCOHOL = "ALCOHOL", "Alcohol"
    SSP = "SSP", "SSP"


class DepartmentConfig(models.Model):
    name = models.CharField(max_length=100, unique=True)
    auto_follow_up_days = models.PositiveIntegerField(default=30)
    predefined_actions = models.JSONField(default=list, blank=True)
    metadata_template = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RoleSetting(models.Model):
    role_name = models.CharField(max_length=50, unique=True)
    can_case_create = models.BooleanField(default=False)
    can_case_edit = models.BooleanField(default=False)
    can_task_create = models.BooleanField(default=False)
    can_task_edit = models.BooleanField(default=False)
    can_note_add = models.BooleanField(default=False)
    can_manage_settings = models.BooleanField(default=False)

    class Meta:
        ordering = ["role_name"]

    def capabilities(self):
        return {
            "case_create": self.can_case_create,
            "case_edit": self.can_case_edit,
            "task_create": self.can_task_create,
            "task_edit": self.can_task_edit,
            "note_add": self.can_note_add,
            "manage_settings": self.can_manage_settings,
        }


DEFAULT_DEPARTMENTS = [
    {
        "name": "ANC",
        "predefined_actions": ["ANC Visit", "USG Review", "BP & Labs"],
        "metadata_template": {"lmp": "Date", "edd": "Date"},
    },
    {
        "name": "Surgery",
        "predefined_actions": ["LAB TEST", "Xray", "ECG", "Inform Anesthetist"],
        "metadata_template": {"surgical_pathway": "String", "surgery_date": "Date"},
    },
    {
        "name": "Non Surgical",
        "predefined_actions": ["Consultant Review", "Opinion for other consultant"],
        "metadata_template": {"review_date": "Date", "review_frequency": "String"},
    },
]

DEFAULT_ROLE_SETTINGS = {
    "Admin": {
        "can_case_create": True,
        "can_case_edit": True,
        "can_task_create": True,
        "can_task_edit": True,
        "can_note_add": True,
        "can_manage_settings": True,
    },
    "Doctor": {
        "can_case_create": True,
        "can_case_edit": True,
        "can_task_create": True,
        "can_task_edit": True,
        "can_note_add": True,
    },
    "Reception": {
        "can_case_create": True,
        "can_case_edit": True,
        "can_task_create": True,
        "can_note_add": True,
    },
    "Nurse": {
        "can_task_edit": True,
        "can_note_add": True,
    },
    "Caller": {
        "can_note_add": True,
    },
}


def ensure_default_departments():
    for item in DEFAULT_DEPARTMENTS:
        DepartmentConfig.objects.get_or_create(
            name=item["name"],
            defaults={
                "predefined_actions": item["predefined_actions"],
                "metadata_template": item["metadata_template"],
            },
        )


def ensure_default_role_settings():
    for role_name, perms in DEFAULT_ROLE_SETTINGS.items():
        RoleSetting.objects.get_or_create(role_name=role_name, defaults=perms)

class Case(models.Model):
    uhid = models.CharField(max_length=64, unique=True)
    first_name = models.CharField(max_length=100, default="")
    last_name = models.CharField(max_length=100, default="")
    patient_name = models.CharField(max_length=200, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    place = models.CharField(max_length=200, blank=True)
    age = models.PositiveSmallIntegerField(blank=True, null=True)
    phone_number = models.CharField(max_length=10, db_index=True)
    alternate_phone_number = models.CharField(max_length=10, blank=True)
    category = models.ForeignKey(DepartmentConfig, on_delete=models.PROTECT, related_name="cases")
    status = models.CharField(max_length=32, choices=CaseStatus.choices, default=CaseStatus.ACTIVE)

    diagnosis = models.CharField(max_length=255, blank=True)
    ncd_flags = models.JSONField(default=list, blank=True)
    referred_by = models.CharField(max_length=255, blank=True)
    high_risk = models.BooleanField(default=False)

    lmp = models.DateField(blank=True, null=True)
    edd = models.DateField(blank=True, null=True)
    usg_edd = models.DateField(blank=True, null=True)
    surgical_pathway = models.CharField(max_length=32, choices=SurgicalPathway.choices, blank=True)
    surgery_done = models.BooleanField(default=False)
    review_frequency = models.CharField(max_length=20, choices=ReviewFrequency.choices, blank=True)
    review_date = models.DateField(blank=True, null=True)
    surgery_date = models.DateField(blank=True, null=True)

    gravida = models.PositiveSmallIntegerField(blank=True, null=True)
    para = models.PositiveSmallIntegerField(blank=True, null=True)
    abortions = models.PositiveSmallIntegerField(blank=True, null=True)
    living = models.PositiveSmallIntegerField(blank=True, null=True)

    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_cases")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["first_name", "last_name"]),
            models.Index(fields=["patient_name"]),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def clean(self):
        if self.phone_number and (not self.phone_number.isdigit() or len(self.phone_number) != 10):
            raise ValidationError({"phone_number": "Phone number must be exactly 10 digits."})
        if self.alternate_phone_number and (not self.alternate_phone_number.isdigit() or len(self.alternate_phone_number) != 10):
            raise ValidationError({"alternate_phone_number": "Alternate phone number must be exactly 10 digits."})

        if self.status == CaseStatus.ACTIVE:
            duplicate_qs = Case.objects.filter(uhid=self.uhid, status=CaseStatus.ACTIVE)
            if self.pk:
                duplicate_qs = duplicate_qs.exclude(pk=self.pk)
            if duplicate_qs.exists():
                raise ValidationError({"uhid": "No duplicate active cases are allowed for the same UHID."})

        category_name = self.category.name.upper() if self.category_id else ""
        if category_name == "ANC" and (not self.lmp or (not self.edd and not self.usg_edd)):
            raise ValidationError("ANC cases require LMP and at least one EDD (LMP-based or USG-based).")
        if category_name == "ANC":
            g, p, a, l = self.gravida, self.para, self.abortions, self.living
            if None not in (g, p, a, l):
                if p > g:
                    raise ValidationError({"para": "Para (P) cannot exceed Gravida (G)."})
                if a > g:
                    raise ValidationError({"abortions": "Abortions (A) cannot exceed Gravida (G)."})
                if p + a > g:
                    raise ValidationError({"abortions": "The sum of Para and Abortions cannot exceed Gravida."})
        if category_name == "SURGERY":
            if not self.surgical_pathway:
                raise ValidationError({"surgical_pathway": "Please choose surveillance or planned surgery."})
            if self.surgical_pathway == SurgicalPathway.SURVEILLANCE and not self.review_date:
                raise ValidationError({"review_date": "Surveillance cases require a review date."})
            if self.surgical_pathway == SurgicalPathway.PLANNED_SURGERY and not self.surgery_date:
                raise ValidationError({"surgery_date": "Planned surgery cases require a surgery date."})
        if category_name in ["NON SURGICAL", "NON-SURGICAL", "NONSURGICAL"] and not self.review_date:
            raise ValidationError({"review_date": "Non-surgical cases require a review date."})

    def save(self, *args, **kwargs):
        self.patient_name = self.full_name
        super().save(*args, **kwargs)

    @property
    def trimester(self):
        if not self.lmp:
            return None
        weeks = max((timezone.localdate() - self.lmp).days // 7, 0)
        if weeks < 13:
            return "First"
        if weeks < 28:
            return "Second"
        return "Third"

    @property
    def effective_edd(self):
        return self.usg_edd or self.edd

    def __str__(self) -> str:
        return f"{self.uhid} - {self.full_name}"


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

    def clean(self):
        if self.status == TaskStatus.COMPLETED and self.case_id:
            category_name = self.case.category.name.upper()
            if category_name == "ANC" and self.due_date and self.due_date > timezone.localdate():
                raise ValidationError({"status": "ANC tasks cannot be completed before their scheduled due date."})

    def save(self, *args, **kwargs):
        if self.status == TaskStatus.COMPLETED and self.completed_at is None:
            self.completed_at = timezone.now()
        if self.status != TaskStatus.COMPLETED:
            self.completed_at = None
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class CaseActivityLog(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="activity_logs")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class CallLog(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="call_logs")
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, related_name="call_logs")
    outcome = models.CharField(max_length=40, choices=CallOutcome.choices)
    notes = models.TextField(blank=True)
    staff_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="call_logs")
    created_at = models.DateTimeField(auto_now_add=True)

    FAILED_OUTCOMES = {
        CallOutcome.NO_ANSWER,
        CallOutcome.SWITCHED_OFF,
        CallOutcome.CALL_REJECTED,
        CallOutcome.RUDE_BEHAVIOR,
    }

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["case", "-created_at"], name="pat_call_case_created_idx"),
            models.Index(fields=["outcome"], name="pat_call_outcome_idx"),
        ]

    @classmethod
    def summarize_case(cls, call_logs):
        logs = list(call_logs)
        if not logs:
            return {
                "status": CallCommunicationStatus.NONE,
                "failed_attempt_count": 0,
                "latest_outcome": "",
                "latest_logged_at": None,
            }

        latest = logs[0]
        latest_outcome = latest.outcome
        if latest_outcome == CallOutcome.ANSWERED_CONFIRMED_VISIT:
            return {
                "status": CallCommunicationStatus.CONFIRMED,
                "failed_attempt_count": 0,
                "latest_outcome": latest_outcome,
                "latest_logged_at": latest.created_at,
            }
        if latest_outcome == CallOutcome.PATIENT_SHIFTED:
            status = CallCommunicationStatus.LOST
        elif latest_outcome == CallOutcome.INVALID_NUMBER:
            status = CallCommunicationStatus.INVALID_CONTACT
        elif latest_outcome == CallOutcome.CALL_BACK_LATER:
            status = CallCommunicationStatus.CALL_BACK_LATER
        elif latest_outcome in cls.FAILED_OUTCOMES:
            status = CallCommunicationStatus.NOT_REACHABLE
        else:
            status = CallCommunicationStatus.NONE

        failed_attempt_count = sum(1 for log in logs if log.outcome in cls.FAILED_OUTCOMES)
        return {
            "status": status,
            "failed_attempt_count": failed_attempt_count,
            "latest_outcome": latest_outcome,
            "latest_logged_at": latest.created_at,
        }


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
        start_date = case.lmp or today
        anc_schedule = {
            2: [
                "Routine prenatal check up",
                "Urine pregnancy test",
                "Blood and urine test (ANC profile)",
                "Pregnancy ultrasound scan for cardiac activity",
            ],
            3: [
                "Routine prenatal check up",
                "First trimester combined test",
                "NT ultrasound scan (sonography) and a double marker test",
            ],
            4: ["Routine prenatal check up"],
            5: ["Routine prenatal check up", "Anomaly or ultrasound level II scan"],
            6: ["Routine prenatal check up", "First dose of Tetanus Toxoid (TT) injection"],
            7: [
                "Routine prenatal check up (once every two weeks)",
                "Second dose of Tetanus Toxoid (TT) injection",
                "Growth and fetal wellbeing ultrasound scan",
                "Blood test (CBC/Urine R/OGCT)",
            ],
            8: ["Routine prenatal check up (once every two weeks)"],
            9: [
                "Routine prenatal check up (once every week)",
                "Growth ultrasound scan",
                "Nonstress test (NST)",
                "Blood test (CBC/HIV/HBsAg)",
            ],
        }
        for month, titles in anc_schedule.items():
            due = start_date + timedelta(days=(month - 1) * 28)
            if case.effective_edd and due > case.effective_edd:
                due = case.effective_edd
            for title in titles:
                task_type = TaskType.VISIT
                if "test" in title.lower() or "blood" in title.lower() or "urine" in title.lower():
                    task_type = TaskType.LAB
                elif "scan" in title.lower() or "injection" in title.lower() or "nst" in title.lower():
                    task_type = TaskType.PROCEDURE
                tasks.append((title, due, task_type, f"ANC month {month}"))
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
        action = case.category.predefined_actions[0] if case.category.predefined_actions else "Review by consultant"
        tasks.append((action, review, TaskType.CUSTOM, case.get_review_frequency_display() or "Review"))

    created = []
    for title, due_date, task_type, frequency_label in tasks:
        created.append(
            Task.objects.create(
                case=case,
                title=title,
                due_date=due_date,
                task_type=task_type,
                frequency_label=frequency_label,
                created_by=actor,
            )
        )
    return created
