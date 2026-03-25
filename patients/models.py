from datetime import datetime, time as dt_time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .theme import get_default_category_theme, normalize_hex_color, normalize_theme_tokens


class CaseStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    LOSS_TO_FOLLOW_UP = "LOSS_TO_FOLLOW_UP", "Loss to Follow-up"


class CasePrefix(models.TextChoices):
    MR = "MR", "Mr."
    MS = "MS", "Ms."
    MRS = "MRS", "Mrs."


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


RCH_REMINDER_TASK_TITLE = "Update RCH Number"
RCH_REMINDER_INTERVAL_DAYS = 14
RCH_REMINDER_FREQUENCY_LABEL = "RCH reminder"
QUICK_ENTRY_DETAILS_TASK_TITLE = "Details need to be filled"
QUICK_ENTRY_FREQUENCY_LABEL = "Quick entry"
TEMP_PATIENT_ID_PREFIX = "TMP"
STAFF_ROLE_NAME = "Staff"
STAFF_PILOT_ROLE_NAME = "Staff Pilot"
DEVICE_APPROVAL_MAX_APPROVED = 3


def normalize_backup_schedule_time(value):
    if value in (None, ""):
        raise ValueError("Backup times must use HH:MM 24-hour format.")
    if isinstance(value, dt_time):
        return value.replace(second=0, microsecond=0).strftime("%H:%M")
    try:
        parsed = datetime.strptime(str(value).strip(), "%H:%M").time()
    except ValueError as exc:
        raise ValueError("Backup times must use HH:MM 24-hour format.") from exc
    return parsed.strftime("%H:%M")


def normalize_case_name(value):
    normalized = " ".join((value or "").split())
    if not normalized:
        return ""
    return normalized.title()


def normalize_category_name(value):
    return " ".join((value or "").replace("-", " ").split()).upper()


def generate_temporary_patient_uhid(today=None):
    quick_entry_day = today or timezone.localdate()
    prefix = f"{TEMP_PATIENT_ID_PREFIX}-{quick_entry_day:%Y%m%d}-"
    existing_uhids = set(Patient.objects.filter(uhid__startswith=prefix).values_list("uhid", flat=True))
    next_sequence = 1
    candidate = f"{prefix}{next_sequence:03d}"
    while candidate in existing_uhids:
        next_sequence += 1
        candidate = f"{prefix}{next_sequence:03d}"
    return candidate


def generate_quick_entry_uhid(today=None):
    return generate_temporary_patient_uhid(today=today)


def is_temporary_patient_uhid(value):
    normalized = str(value or "").strip().upper()
    return normalized.startswith(f"{TEMP_PATIENT_ID_PREFIX}-")


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


class ActivityEventType(models.TextChoices):
    SYSTEM = "SYSTEM", "System"
    TASK = "TASK", "Task"
    NOTE = "NOTE", "Note"
    CALL = "CALL", "Call"


class SurgicalPathway(models.TextChoices):
    PLANNED_SURGERY = "PLANNED_SURGERY", "Planned for surgery"
    SURVEILLANCE = "SURVEILLANCE", "Surveillance only"


class ReviewFrequency(models.TextChoices):
    MONTHLY = "MONTHLY", "Monthly"
    QUARTERLY = "QUARTERLY", "Every 3 months"
    HALF_YEARLY = "HALF_YEARLY", "Every 6 months"
    YEARLY = "YEARLY", "Yearly"


class StarterTaskAnchor(models.TextChoices):
    LMP = "lmp", "LMP"
    EFFECTIVE_EDD = "effective_edd", "EDD"
    SURGERY_DATE = "surgery_date", "Surgery date"
    REVIEW_DATE = "review_date", "Review date"
    CREATED_DATE = "created_date", "Case created day"


class StarterTaskAppliesTo(models.TextChoices):
    ALWAYS = "always", "Always"
    PLANNED_SURGERY = "planned_surgery", "Planned surgery"
    SURVEILLANCE = "surveillance", "Surveillance"


class CaseSubcategory(models.TextChoices):
    GENERAL_SURGERY = "GENERAL_SURGERY", "General Surgery"
    ORTHOPEDICS = "ORTHOPEDICS", "Orthopedics"
    PLASTIC_SURGERY = "PLASTIC_SURGERY", "Plastic Surgery"
    PEDIATRIC_SURGERY = "PEDIATRIC_SURGERY", "Pediatric Surgery"
    UROLOGY = "UROLOGY", "Urology"
    ENT = "ENT", "ENT"
    OTHER_SPECIALTY = "OTHER_SPECIALTY", "Other Specialty"
    GENERAL_MEDICINE = "GENERAL_MEDICINE", "General Medicine"
    PSYCHIATRY = "PSYCHIATRY", "Psychiatry"
    CARDIOLOGY_ECHO = "CARDIOLOGY_ECHO", "Cardiology (ECHO)"
    PEDIATRIC = "PEDIATRIC", "Pediatric"
    MEDICAL_ONCOLOGY = "MEDICAL_ONCOLOGY", "Medical Oncology"


SURGERY_CASE_SUBCATEGORY_CHOICES = [
    (CaseSubcategory.GENERAL_SURGERY, CaseSubcategory.GENERAL_SURGERY.label),
    (CaseSubcategory.ORTHOPEDICS, CaseSubcategory.ORTHOPEDICS.label),
    (CaseSubcategory.PLASTIC_SURGERY, CaseSubcategory.PLASTIC_SURGERY.label),
    (CaseSubcategory.PEDIATRIC_SURGERY, CaseSubcategory.PEDIATRIC_SURGERY.label),
    (CaseSubcategory.UROLOGY, CaseSubcategory.UROLOGY.label),
    (CaseSubcategory.ENT, CaseSubcategory.ENT.label),
    (CaseSubcategory.OTHER_SPECIALTY, CaseSubcategory.OTHER_SPECIALTY.label),
]
MEDICINE_CASE_SUBCATEGORY_CHOICES = [
    (CaseSubcategory.GENERAL_MEDICINE, CaseSubcategory.GENERAL_MEDICINE.label),
    (CaseSubcategory.PSYCHIATRY, CaseSubcategory.PSYCHIATRY.label),
    (CaseSubcategory.CARDIOLOGY_ECHO, CaseSubcategory.CARDIOLOGY_ECHO.label),
    (CaseSubcategory.PEDIATRIC, CaseSubcategory.PEDIATRIC.label),
    (CaseSubcategory.MEDICAL_ONCOLOGY, CaseSubcategory.MEDICAL_ONCOLOGY.label),
]
CASE_SUBCATEGORY_GROUP_CHOICES = {
    "surgery": SURGERY_CASE_SUBCATEGORY_CHOICES,
    "medicine": MEDICINE_CASE_SUBCATEGORY_CHOICES,
}
CASE_SUBCATEGORY_DEFAULTS = {
    "surgery": CaseSubcategory.GENERAL_SURGERY,
    "medicine": CaseSubcategory.GENERAL_MEDICINE,
}


def case_subcategory_group_for_category_name(name: str) -> str:
    normalized_name = normalize_category_name(name)
    if normalized_name == "SURGERY":
        return "surgery"
    if normalized_name in {"MEDICINE", "NON SURGICAL", "NONSURGICAL"}:
        return "medicine"
    return ""


def case_subcategory_choices_for_category_name(name: str):
    return CASE_SUBCATEGORY_GROUP_CHOICES.get(case_subcategory_group_for_category_name(name), [])


def valid_case_subcategory_values_for_category_name(name: str):
    return {value for value, _ in case_subcategory_choices_for_category_name(name)}


def default_case_subcategory_for_category_name(name: str) -> str:
    return CASE_SUBCATEGORY_DEFAULTS.get(case_subcategory_group_for_category_name(name), "")


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


class AncHighRiskReason(models.TextChoices):
    TEENAGE_PREGNANCY = "TEENAGE_PREGNANCY", "Teenage pregnancy"
    ANEMIA = "ANEMIA", "Anemia"
    REPEAT_ABORTION = "REPEAT_ABORTION", "Repeat abortion"
    ELDERLY_PRIMI = "ELDERLY_PRIMI", "Elderly primi"
    SHORT_STATURE_HEIGHT = "SHORT_STATURE_HEIGHT", "Short stature height"
    PREVIOUS_LSCS = "PREVIOUS_LSCS", "Previous LSCS"
    PIH = "PIH", "PIH"


class DepartmentConfig(models.Model):
    name = models.CharField(max_length=100, unique=True)
    auto_follow_up_days = models.PositiveIntegerField(default=30)
    predefined_actions = models.JSONField(default=list, blank=True)
    starter_task_templates = models.JSONField(default=list, blank=True)
    metadata_template = models.JSONField(default=dict, blank=True)
    theme_bg_color = models.CharField(max_length=7, blank=True, default="")
    theme_text_color = models.CharField(max_length=7, blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        default_theme = get_default_category_theme(self.name)
        bg_color = (self.theme_bg_color or "").strip()
        text_color = (self.theme_text_color or "").strip()
        self.theme_bg_color = normalize_hex_color(bg_color or default_theme["bg"])
        self.theme_text_color = normalize_hex_color(text_color or default_theme["text"])
        self.starter_task_templates = normalize_starter_task_templates(
            self.starter_task_templates or [],
            workflow_key=workflow_key_for_category_name(self.name),
        )
        super().save(*args, **kwargs)


class RoleSetting(models.Model):
    role_name = models.CharField(max_length=50, unique=True)
    can_case_create = models.BooleanField(default=False)
    can_case_edit = models.BooleanField(default=False)
    can_task_create = models.BooleanField(default=False)
    can_task_edit = models.BooleanField(default=False)
    can_note_add = models.BooleanField(default=False)
    can_patient_merge = models.BooleanField(default=False)
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
            "patient_merge": self.can_patient_merge,
            "manage_settings": self.can_manage_settings,
        }

    def field_capabilities(self):
        return {
            "can_case_create": self.can_case_create,
            "can_case_edit": self.can_case_edit,
            "can_task_create": self.can_task_create,
            "can_task_edit": self.can_task_edit,
            "can_note_add": self.can_note_add,
            "can_patient_merge": self.can_patient_merge,
            "can_manage_settings": self.can_manage_settings,
        }


class ThemeSettings(models.Model):
    tokens = models.JSONField(default=dict, blank=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        self.tokens = normalize_theme_tokens(self.tokens)
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        return cls.objects.get_or_create(pk=1)[0]


class UserAdminNote(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="admin_note")
    temporary_password_note = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_user_admin_notes",
    )

    def __str__(self) -> str:
        return f"Admin note for {self.user}"


class Patient(models.Model):
    uhid = models.CharField(max_length=64, unique=True)
    is_temporary_id = models.BooleanField(default=False)
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_patients",
    )
    prefix = models.CharField(max_length=3, choices=CasePrefix.choices, blank=True, default="")
    first_name = models.CharField(max_length=100, default="")
    last_name = models.CharField(max_length=100, default="")
    patient_name = models.CharField(max_length=200, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    place = models.CharField(max_length=200, blank=True)
    age = models.PositiveSmallIntegerField(blank=True, null=True)
    phone_number = models.CharField(max_length=10, blank=True, db_index=True)
    alternate_phone_number = models.CharField(max_length=10, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_patients",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["patient_name", "uhid"]
        indexes = [
            models.Index(fields=["first_name", "last_name"]),
            models.Index(fields=["patient_name"]),
        ]

    @property
    def identity_name(self):
        return " ".join(part for part in [self.first_name, self.last_name] if part)

    @property
    def full_name(self):
        prefix_label = self.get_prefix_display() if self.prefix else ""
        return " ".join(part for part in [prefix_label, self.identity_name] if part)

    @property
    def is_merged(self):
        return self.merged_into_id is not None

    def _normalize_identity_fields(self):
        self.first_name = normalize_case_name(self.first_name)
        self.last_name = normalize_case_name(self.last_name)
        self.place = normalize_case_name(self.place)
        self.patient_name = self.full_name

    def clean(self):
        self.uhid = " ".join((self.uhid or "").split()).upper()
        phone_errors = {}
        if self.phone_number and (not self.phone_number.isdigit() or len(self.phone_number) != 10):
            phone_errors["phone_number"] = "Phone number must be exactly 10 digits."
        if self.alternate_phone_number and (
            not self.alternate_phone_number.isdigit() or len(self.alternate_phone_number) != 10
        ):
            phone_errors["alternate_phone_number"] = "Alternate phone number must be exactly 10 digits."
        if phone_errors:
            raise ValidationError(phone_errors)
        if self.merged_into_id and self.merged_into_id == self.pk:
            raise ValidationError({"merged_into": "A patient cannot be merged into itself."})

    def sync_case_mirrors(self):
        if not self.pk:
            return
        self.cases.update(
            uhid=self.uhid,
            prefix=self.prefix,
            first_name=self.first_name,
            last_name=self.last_name,
            patient_name=self.patient_name,
            gender=self.gender,
            date_of_birth=self.date_of_birth,
            place=self.place,
            age=self.age,
            phone_number=self.phone_number,
            alternate_phone_number=self.alternate_phone_number,
            updated_at=timezone.now(),
        )

    def save(self, *args, **kwargs):
        self.uhid = " ".join((self.uhid or "").split()).upper()
        self.is_temporary_id = is_temporary_patient_uhid(self.uhid)
        if self.date_of_birth:
            today = timezone.localdate()
            years = today.year - self.date_of_birth.year
            has_had_birthday = (today.month, today.day) >= (self.date_of_birth.month, self.date_of_birth.day)
            self.age = years if has_had_birthday else years - 1
        self._normalize_identity_fields()
        super().save(*args, **kwargs)
        self.sync_case_mirrors()

    def __str__(self) -> str:
        return f"{self.uhid} - {self.full_name or self.patient_name}"


class PatientDataBackupScheduleMode(models.TextChoices):
    DAILY = "DAILY", "1 per day"
    TWICE_DAILY = "TWICE_DAILY", "2 per day (12:00 AM and 12:00 PM)"
    CUSTOM = "CUSTOM", "Custom timings"


class PatientDataBackupStatus(models.TextChoices):
    NEVER = "NEVER", "Never run"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


class PatientDataBackupTrigger(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    DAILY_SCHEDULED = "DAILY_SCHEDULED", "Daily scheduled backup"
    MONTHLY_SCHEDULED = "MONTHLY_SCHEDULED", "Monthly scheduled backup"
    YEARLY_SCHEDULED = "YEARLY_SCHEDULED", "Yearly scheduled backup"
    SCHEDULED = "SCHEDULED", "Scheduled"
    IMPORT_SAFETY = "IMPORT_SAFETY", "Import safety"


class PatientDataBackupSchedule(models.Model):
    DAILY_RETENTION_COUNT = 30
    MONTHLY_BACKUP_TIME = dt_time(hour=0, minute=0)
    YEARLY_BACKUP_TIME = dt_time(hour=0, minute=0)

    enabled = models.BooleanField(default=False)
    schedule_mode = models.CharField(
        max_length=16,
        choices=PatientDataBackupScheduleMode.choices,
        default=PatientDataBackupScheduleMode.DAILY,
    )
    daily_time = models.TimeField(default=dt_time(hour=2, minute=0))
    custom_times = models.JSONField(default=list, blank=True)
    retention_count = models.PositiveIntegerField(default=30)
    last_backup_at = models.DateTimeField(null=True, blank=True)
    last_backup_path = models.CharField(max_length=500, blank=True, default="")
    last_backup_status = models.CharField(
        max_length=16,
        choices=PatientDataBackupStatus.choices,
        default=PatientDataBackupStatus.NEVER,
    )
    last_backup_trigger = models.CharField(
        max_length=32,
        choices=PatientDataBackupTrigger.choices,
        blank=True,
        default="",
    )
    last_backup_error = models.TextField(blank=True, default="")
    last_daily_backup_at = models.DateTimeField(null=True, blank=True)
    last_monthly_backup_at = models.DateTimeField(null=True, blank=True)
    last_yearly_backup_at = models.DateTimeField(null=True, blank=True)
    run_lock_until = models.DateTimeField(null=True, blank=True)
    run_lock_token = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        self.schedule_mode = PatientDataBackupScheduleMode.DAILY
        self.custom_times = sorted(
            dict.fromkeys(normalize_backup_schedule_time(value) for value in (self.custom_times or []))
        )
        if self.retention_count < 1:
            self.retention_count = self.DAILY_RETENTION_COUNT
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def schedule_summary(self):
        if not self.enabled:
            return "Disabled"
        return (
            f"Daily at {self.daily_schedule_time_label()}, "
            "monthly on the 1st at 12:00 AM, yearly on Jan 1 at 12:00 AM"
        )

    def daily_schedule_time_label(self):
        return self.daily_time.strftime("%I:%M %p").lstrip("0")

    @staticmethod
    def _midnight_label():
        return "12:00 AM"

    @staticmethod
    def _aware_datetime(target_date, target_time):
        tz = timezone.get_current_timezone()
        return timezone.make_aware(datetime.combine(target_date, target_time), tz)

    def _monthly_backup_datetime(self, year, month):
        return self._aware_datetime(datetime(year=year, month=month, day=1).date(), self.MONTHLY_BACKUP_TIME)

    def _yearly_backup_datetime(self, year):
        return self._aware_datetime(datetime(year=year, month=1, day=1).date(), self.YEARLY_BACKUP_TIME)

    def latest_due_backup_at_for(self, schedule_key, reference_time=None):
        if not self.enabled:
            return None
        reference_time = timezone.localtime(reference_time or timezone.now())
        if schedule_key == "daily":
            today_backup = self._aware_datetime(reference_time.date(), self.daily_time)
            if today_backup <= reference_time:
                return today_backup
            return self._aware_datetime(reference_time.date() - timedelta(days=1), self.daily_time)
        if schedule_key == "monthly":
            current_month_backup = self._monthly_backup_datetime(reference_time.year, reference_time.month)
            if current_month_backup <= reference_time:
                return current_month_backup
            previous_month_date = reference_time.date().replace(day=1) - timedelta(days=1)
            return self._monthly_backup_datetime(previous_month_date.year, previous_month_date.month)
        if schedule_key == "yearly":
            current_year_backup = self._yearly_backup_datetime(reference_time.year)
            if current_year_backup <= reference_time:
                return current_year_backup
            return self._yearly_backup_datetime(reference_time.year - 1)
        return None

    def next_backup_at(self, reference_time=None):
        next_backups = [
            self.next_backup_at_for("daily", reference_time),
            self.next_backup_at_for("monthly", reference_time),
            self.next_backup_at_for("yearly", reference_time),
        ]
        next_backups = [scheduled_at for scheduled_at in next_backups if scheduled_at is not None]
        return min(next_backups) if next_backups else None

    def next_backup_at_for(self, schedule_key, reference_time=None):
        if not self.enabled:
            return None
        reference_time = timezone.localtime(reference_time or timezone.now())
        if schedule_key == "daily":
            today_backup = self._aware_datetime(reference_time.date(), self.daily_time)
            if today_backup > reference_time:
                return today_backup
            return self._aware_datetime(reference_time.date() + timedelta(days=1), self.daily_time)
        if schedule_key == "monthly":
            current_month_backup = self._monthly_backup_datetime(reference_time.year, reference_time.month)
            if current_month_backup > reference_time:
                return current_month_backup
            next_month_anchor = reference_time.date().replace(day=28) + timedelta(days=4)
            next_month_date = next_month_anchor.replace(day=1)
            return self._monthly_backup_datetime(next_month_date.year, next_month_date.month)
        if schedule_key == "yearly":
            current_year_backup = self._yearly_backup_datetime(reference_time.year)
            if current_year_backup > reference_time:
                return current_year_backup
            return self._yearly_backup_datetime(reference_time.year + 1)
        return None

    def last_backup_at_for(self, schedule_key):
        if schedule_key == "daily":
            return self.last_daily_backup_at
        if schedule_key == "monthly":
            return self.last_monthly_backup_at
        if schedule_key == "yearly":
            return self.last_yearly_backup_at
        return None

    def due_scheduled_runs(self, reference_time=None):
        if not self.enabled:
            return []
        runs = []
        for schedule_key in ("yearly", "monthly", "daily"):
            due_at = self.latest_due_backup_at_for(schedule_key, reference_time)
            if due_at is None:
                continue
            last_backup_at = self.last_backup_at_for(schedule_key)
            if last_backup_at is None or last_backup_at < due_at:
                runs.append({"schedule_key": schedule_key, "due_at": due_at})
        return runs

    def schedule_rows(self, reference_time=None):
        return [
            {
                "key": "daily",
                "label": "Daily backups",
                "schedule": f"Every day at {self.daily_schedule_time_label()}",
                "retention": f"Keep last {self.retention_count} daily backups",
                "last_backup_at": self.last_daily_backup_at,
                "next_backup_at": self.next_backup_at_for("daily", reference_time),
            },
            {
                "key": "monthly",
                "label": "Monthly backups",
                "schedule": f"Every 1st of the month at {self._midnight_label()}",
                "retention": "Keep all monthly backups",
                "last_backup_at": self.last_monthly_backup_at,
                "next_backup_at": self.next_backup_at_for("monthly", reference_time),
            },
            {
                "key": "yearly",
                "label": "Yearly backups",
                "schedule": f"Every Jan 1 at {self._midnight_label()}",
                "retention": "Keep all yearly backups",
                "last_backup_at": self.last_yearly_backup_at,
                "next_backup_at": self.next_backup_at_for("yearly", reference_time),
            },
        ]

    @classmethod
    def record_backup_success(cls, *, backup_path, trigger, backup_at=None, schedule_key=None):
        schedule = cls.get_solo()
        schedule.last_backup_at = backup_at or timezone.now()
        schedule.last_backup_path = str(backup_path)
        schedule.last_backup_status = PatientDataBackupStatus.SUCCESS
        schedule.last_backup_trigger = trigger
        schedule.last_backup_error = ""
        update_fields = [
            "last_backup_at",
            "last_backup_path",
            "last_backup_status",
            "last_backup_trigger",
            "last_backup_error",
            "updated_at",
        ]
        if schedule_key == "daily":
            schedule.last_daily_backup_at = schedule.last_backup_at
            update_fields.append("last_daily_backup_at")
        elif schedule_key == "monthly":
            schedule.last_monthly_backup_at = schedule.last_backup_at
            update_fields.append("last_monthly_backup_at")
        elif schedule_key == "yearly":
            schedule.last_yearly_backup_at = schedule.last_backup_at
            update_fields.append("last_yearly_backup_at")
        schedule.save(update_fields=update_fields)

    @classmethod
    def record_backup_failure(cls, *, error, trigger="", backup_at=None):
        schedule = cls.get_solo()
        if backup_at is not None:
            schedule.last_backup_at = backup_at
        schedule.last_backup_status = PatientDataBackupStatus.FAILED
        schedule.last_backup_trigger = trigger
        schedule.last_backup_error = error
        schedule.save(
            update_fields=[
                "last_backup_at",
                "last_backup_status",
                "last_backup_trigger",
                "last_backup_error",
                "updated_at",
            ]
        )


class DeviceApprovalPolicy(models.Model):
    enabled = models.BooleanField(default=False)
    target_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="device_approval_policies")
    target_groups = models.ManyToManyField("auth.Group", blank=True, related_name="device_approval_policies")
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def targets_user(self, user) -> bool:
        if not self.enabled or not getattr(user, "is_authenticated", False):
            return False
        return self.target_users.filter(pk=user.pk).exists()


class StaffDeviceCredentialStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REVOKED = "REVOKED", "Revoked"


class StaffDeviceCredential(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_credentials")
    status = models.CharField(
        max_length=16,
        choices=StaffDeviceCredentialStatus.choices,
        default=StaffDeviceCredentialStatus.PENDING,
    )
    device_label = models.CharField(max_length=120)
    credential_id = models.CharField(max_length=255, unique=True)
    public_key = models.TextField()
    sign_count = models.PositiveIntegerField(default=0)
    credential_type = models.CharField(max_length=32, blank=True)
    aaguid = models.CharField(max_length=64, blank=True)
    transports = models.JSONField(default=list, blank=True)
    authenticator_attachment = models.CharField(max_length=32, blank=True)
    device_type = models.CharField(max_length=32, blank=True)
    backed_up = models.BooleanField(default=False)
    user_agent = models.TextField(blank=True)
    trusted_token_hash = models.CharField(max_length=128, blank=True, default="")
    trusted_token_created_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_device_credentials",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_device_credentials",
    )
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["user__username", "status", "-created_at"]
        indexes = [
            models.Index(fields=["user", "status"], name="pat_dev_user_status_idx"),
        ]

    def clear_trusted_token(self):
        self.trusted_token_hash = ""
        self.trusted_token_created_at = None

    def __str__(self) -> str:
        return f"{self.user} - {self.device_label}"


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
        "name": "Medicine",
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
        "can_patient_merge": True,
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
        default_theme = get_default_category_theme(item["name"])
        DepartmentConfig.objects.get_or_create(
            name=item["name"],
            defaults={
                "predefined_actions": item["predefined_actions"],
                "starter_task_templates": default_starter_task_templates_for_category_name(
                    item["name"],
                    item["predefined_actions"],
                ),
                "metadata_template": item["metadata_template"],
                "theme_bg_color": default_theme["bg"],
                "theme_text_color": default_theme["text"],
            },
        )


def ensure_default_role_settings():
    for role_name, perms in DEFAULT_ROLE_SETTINGS.items():
        RoleSetting.objects.get_or_create(role_name=role_name, defaults=perms)


def clone_role_setting(source_role_name=STAFF_ROLE_NAME, target_role_name=STAFF_PILOT_ROLE_NAME):
    source = RoleSetting.objects.get(role_name=source_role_name)
    target, _ = RoleSetting.objects.update_or_create(
        role_name=target_role_name,
        defaults=source.field_capabilities(),
    )
    return target

class Case(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="cases", null=True, blank=True)
    uhid = models.CharField(max_length=64, blank=True, db_index=True)
    prefix = models.CharField(max_length=3, choices=CasePrefix.choices, blank=True, default="")
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
    subcategory = models.CharField(max_length=40, choices=CaseSubcategory.choices, blank=True, default="")
    status = models.CharField(max_length=32, choices=CaseStatus.choices, default=CaseStatus.ACTIVE)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(blank=True, null=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_cases",
    )

    diagnosis = models.CharField(max_length=255, blank=True)
    ncd_flags = models.JSONField(default=list, blank=True)
    referred_by = models.CharField(max_length=255, blank=True)
    high_risk = models.BooleanField(default=False)
    anc_high_risk_reasons = models.JSONField(default=list, blank=True)
    rch_number = models.CharField(max_length=32, blank=True)
    rch_bypass = models.BooleanField(default=False)

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
    ftnd = models.PositiveSmallIntegerField(default=0, blank=True)
    lscs = models.PositiveSmallIntegerField(default=0, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_cases")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["patient"]),
            models.Index(fields=["first_name", "last_name"]),
            models.Index(fields=["patient_name"]),
        ]

    @property
    def identity_name(self):
        return " ".join(part for part in [self.first_name, self.last_name] if part)

    @property
    def full_name(self):
        prefix_label = self.get_prefix_display() if self.prefix else ""
        return " ".join(part for part in [prefix_label, self.identity_name] if part)

    def sync_identity_from_patient(self):
        if not self.patient_id:
            return
        self.uhid = self.patient.uhid
        self.prefix = self.patient.prefix
        self.first_name = self.patient.first_name
        self.last_name = self.patient.last_name
        self.patient_name = self.patient.patient_name or self.patient.full_name
        self.gender = self.patient.gender
        self.date_of_birth = self.patient.date_of_birth
        self.place = self.patient.place
        self.age = self.patient.age
        self.phone_number = self.patient.phone_number
        self.alternate_phone_number = self.patient.alternate_phone_number

    def ensure_patient_link(self):
        if self.patient_id:
            return self.patient

        normalized_uhid = " ".join((self.uhid or "").split()).upper()
        if not normalized_uhid:
            normalized_uhid = generate_temporary_patient_uhid()
            self.uhid = normalized_uhid

        patient_defaults = {
            "prefix": self.prefix or "",
            "first_name": self.first_name or "",
            "last_name": self.last_name or "",
            "gender": self.gender or "",
            "date_of_birth": self.date_of_birth,
            "place": self.place or "",
            "age": self.age,
            "phone_number": self.phone_number or "",
            "alternate_phone_number": self.alternate_phone_number or "",
            "created_by": self.created_by,
            "is_temporary_id": is_temporary_patient_uhid(normalized_uhid),
        }
        patient, created = Patient.objects.get_or_create(uhid=normalized_uhid, defaults=patient_defaults)
        if not created:
            changed = False
            if self.created_by_id and not patient.created_by_id:
                patient.created_by = self.created_by
                changed = True
            for field_name, field_value in patient_defaults.items():
                if field_name in {"created_by", "is_temporary_id"}:
                    continue
                existing_value = getattr(patient, field_name)
                if field_value not in (None, "") and existing_value in (None, ""):
                    setattr(patient, field_name, field_value)
                    changed = True
            next_temporary_flag = is_temporary_patient_uhid(normalized_uhid)
            if patient.is_temporary_id != next_temporary_flag:
                patient.is_temporary_id = next_temporary_flag
                changed = True
            if changed:
                patient.full_clean()
                patient.save()
        self.patient = patient
        return patient

    def sync_patient_from_case(self):
        if not self.patient_id:
            return None
        patient = self.patient
        patient.uhid = self.uhid
        patient.prefix = self.prefix
        patient.first_name = self.first_name
        patient.last_name = self.last_name
        patient.patient_name = self.patient_name
        patient.gender = self.gender
        patient.date_of_birth = self.date_of_birth
        patient.place = self.place
        patient.age = self.age
        patient.phone_number = self.phone_number
        patient.alternate_phone_number = self.alternate_phone_number
        return patient

    def _normalize_identity_fields(self):
        self.first_name = normalize_case_name(self.first_name)
        self.last_name = normalize_case_name(self.last_name)
        self.place = normalize_case_name(self.place)
        self.patient_name = self.full_name

    def set_archived(self, *, archived, user=None):
        if archived:
            self.is_archived = True
            self.archived_at = timezone.now()
            self.archived_by = user if getattr(user, "is_authenticated", False) else None
        else:
            self.is_archived = False
            self.archived_at = None
            self.archived_by = None

    def clean(self):
        if self.patient_id:
            if getattr(self.patient, "is_merged", False):
                raise ValidationError({"patient": "Merged patients cannot receive new cases."})
            self.sync_identity_from_patient()
        phone_errors = {}
        if self.phone_number and (not self.phone_number.isdigit() or len(self.phone_number) != 10):
            phone_errors["phone_number"] = "Phone number must be exactly 10 digits."
        if self.alternate_phone_number and (not self.alternate_phone_number.isdigit() or len(self.alternate_phone_number) != 10):
            phone_errors["alternate_phone_number"] = "Alternate phone number must be exactly 10 digits."
        if phone_errors:
            raise ValidationError(phone_errors)

        valid_anc_reason_values = {value for value, _ in AncHighRiskReason.choices}
        raw_reasons = self.anc_high_risk_reasons or []
        if not isinstance(raw_reasons, list):
            raw_reasons = []
        self.anc_high_risk_reasons = []
        for reason in raw_reasons:
            if reason in valid_anc_reason_values and reason not in self.anc_high_risk_reasons:
                self.anc_high_risk_reasons.append(reason)

        category_name = normalize_category_name(self.category.name) if self.category_id else ""
        valid_subcategories = valid_case_subcategory_values_for_category_name(category_name)
        self.subcategory = " ".join((self.subcategory or "").split()).upper()
        if valid_subcategories:
            if self.subcategory and self.subcategory not in valid_subcategories:
                if getattr(self, "_skip_workflow_validation", False):
                    self.subcategory = ""
                else:
                    raise ValidationError({"subcategory": "Please choose a valid subcategory for this category."})
        else:
            self.subcategory = ""

        if getattr(self, "_skip_workflow_validation", False):
            if category_name != "ANC":
                self.anc_high_risk_reasons = []
                self.rch_number = ""
                self.rch_bypass = False
                self.ftnd = 0
                self.lscs = 0
            return
        if valid_subcategories and not self.subcategory:
            raise ValidationError({"subcategory": "Please choose a subcategory."})
        if category_name == "ANC" and (not self.lmp or (not self.edd and not self.usg_edd)):
            raise ValidationError("ANC cases require LMP and at least one EDD (LMP-based or USG-based).")
        if category_name == "ANC":
            self.rch_number = (self.rch_number or "").strip()
            if self.rch_number and not self.rch_number.isdigit():
                raise ValidationError({"rch_number": "RCH number must contain digits only."})
            if not self.rch_number and not self.rch_bypass:
                raise ValidationError({"rch_number": "Enter RCH number or bypass it for now."})
            if self.rch_number:
                self.rch_bypass = False
            g, p, a, l = self.gravida, self.para, self.abortions, self.living
            if None not in (g, p, a, l):
                if p > g:
                    raise ValidationError({"para": "Para (P) cannot exceed Gravida (G)."})
                if a > g:
                    raise ValidationError({"abortions": "Abortions (A) cannot exceed Gravida (G)."})
                if p + a > g:
                    raise ValidationError({"abortions": "The sum of Para and Abortions cannot exceed Gravida."})
            ftnd = self.ftnd or 0
            lscs = self.lscs or 0
            if not p or self.is_primi:
                self.ftnd = 0
                self.lscs = 0
                ftnd = 0
                lscs = 0
            elif ftnd + lscs > p:
                self.ftnd = 0
                self.lscs = 0
                ftnd = 0
                lscs = 0
            if p and not self.is_primi and ftnd + lscs != p:
                raise ValidationError(
                    {
                        "ftnd": "FTND and LSCS together must equal Para.",
                        "lscs": "FTND and LSCS together must equal Para.",
                    }
                )
            if self.high_risk and not self.anc_high_risk_reasons:
                raise ValidationError({"anc_high_risk_reasons": "Select at least one ANC high-risk reason."})
            if not self.high_risk:
                self.anc_high_risk_reasons = []
        else:
            self.anc_high_risk_reasons = []
            self.rch_number = ""
            self.rch_bypass = False
            self.ftnd = 0
            self.lscs = 0
        if category_name == "SURGERY":
            if not self.surgical_pathway:
                raise ValidationError({"surgical_pathway": "Please choose surveillance or planned surgery."})
            if self.surgical_pathway == SurgicalPathway.SURVEILLANCE and not self.review_date:
                raise ValidationError({"review_date": "Surveillance cases require a review date."})
            if self.surgical_pathway == SurgicalPathway.PLANNED_SURGERY and not self.surgery_date:
                raise ValidationError({"surgery_date": "Planned surgery cases require a surgery date."})
        if category_name in ["MEDICINE", "NON SURGICAL", "NON-SURGICAL", "NONSURGICAL"] and not self.review_date:
            raise ValidationError({"review_date": "Medicine cases require a review date."})

    def save(self, *args, **kwargs):
        tracked_name_fields = {"prefix", "first_name", "last_name", "patient_name", "place"}
        patient_mirror_fields = {
            "uhid",
            "prefix",
            "first_name",
            "last_name",
            "patient_name",
            "gender",
            "date_of_birth",
            "place",
            "age",
            "phone_number",
            "alternate_phone_number",
        }
        update_fields = kwargs.get("update_fields")
        should_sync_names = update_fields is None
        should_push_identity_to_patient = update_fields is None

        if update_fields is not None:
            update_fields = set(update_fields)
            should_sync_names = bool(tracked_name_fields & update_fields)
            should_push_identity_to_patient = bool(patient_mirror_fields & update_fields)
            if self.patient_id and should_push_identity_to_patient:
                update_fields.update(patient_mirror_fields)
            if should_sync_names:
                update_fields.update(tracked_name_fields)
            kwargs["update_fields"] = tuple(sorted(update_fields))

        self.ensure_patient_link()
        if should_sync_names:
            self._normalize_identity_fields()
        if self.patient_id and should_push_identity_to_patient:
            patient = self.sync_patient_from_case()
            patient.save()
            self.sync_identity_from_patient()
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

    @property
    def anc_high_risk_reason_labels(self):
        choice_map = dict(AncHighRiskReason.choices)
        return [choice_map[value] for value in (self.anc_high_risk_reasons or []) if value in choice_map]

    @property
    def is_primi(self):
        return (self.gravida, self.para, self.abortions, self.living) == (1, 0, 0, 0)

    @property
    def show_delivery_mode_history(self):
        return (self.para or 0) > 0 and not self.is_primi

    @property
    def delivery_mode_total(self):
        return (self.ftnd or 0) + (self.lscs or 0)

    @property
    def obstetric_summary(self):
        if all(value is None for value in (self.gravida, self.para, self.abortions, self.living)):
            return ""
        summary = (
            f"G{self.gravida or 0} "
            f"P{self.para or 0} "
            f"A{self.abortions or 0} "
            f"L{self.living or 0}"
        )
        if self.show_delivery_mode_history:
            summary += f" | FTND {self.ftnd or 0} LSCS {self.lscs or 0}"
        return summary

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


class VitalEntry(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="vitals")
    recorded_at = models.DateTimeField(default=timezone.now)
    bp_systolic = models.PositiveSmallIntegerField(blank=True, null=True)
    bp_diastolic = models.PositiveSmallIntegerField(blank=True, null=True)
    pr = models.PositiveSmallIntegerField(blank=True, null=True)
    spo2 = models.PositiveSmallIntegerField(blank=True, null=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    hemoglobin = models.DecimalField(max_digits=4, decimal_places=1, blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_vitals",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_vitals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [
            models.Index(fields=["case", "-recorded_at"], name="pat_vitals_case_recorded_idx"),
        ]

    @property
    def hemoglobin_out_of_range(self):
        if self.hemoglobin is None:
            return False
        return self.hemoglobin < 4 or self.hemoglobin > 13

    def __str__(self) -> str:
        return f"Vitals for {self.case.uhid} @ {self.recorded_at:%Y-%m-%d %H:%M}"


class CaseActivityLog(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="activity_logs")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    event_type = models.CharField(max_length=16, choices=ActivityEventType.choices, default=ActivityEventType.SYSTEM)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["case", "event_type", "-created_at"], name="pat_act_case_type_created_idx"),
        ]


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


def is_anc_case(case: Case) -> bool:
    return bool(case and case.category_id and normalize_category_name(case.category.name) == "ANC")


def workflow_key_for_category_name(name: str) -> str:
    normalized_name = normalize_category_name(name)
    if normalized_name == "ANC":
        return "anc"
    if normalized_name == "SURGERY":
        return "surgery"
    if normalized_name in {"MEDICINE", "NON SURGICAL", "NONSURGICAL"}:
        return "medicine"
    return "generic"


def workflow_key_for_case(case: Case) -> str:
    if not case or not getattr(case, "category_id", None):
        return "generic"
    return workflow_key_for_category_name(case.category.name)


def open_rch_reminder_queryset(case: Case):
    return case.tasks.filter(title=RCH_REMINDER_TASK_TITLE, status=TaskStatus.SCHEDULED)


def ensure_rch_reminder_task(case: Case, actor, due_date=None):
    if not is_anc_case(case):
        return None
    if case.rch_number or not case.rch_bypass:
        return None
    if open_rch_reminder_queryset(case).exists():
        return None
    reminder_due_date = due_date or (timezone.localdate() + timedelta(days=RCH_REMINDER_INTERVAL_DAYS))
    return Task.objects.create(
        case=case,
        title=RCH_REMINDER_TASK_TITLE,
        due_date=reminder_due_date,
        task_type=TaskType.CALL,
        frequency_label=RCH_REMINDER_FREQUENCY_LABEL,
        created_by=actor,
    )


def cancel_open_rch_reminders(case: Case) -> int:
    reminder_ids = list(open_rch_reminder_queryset(case).values_list("id", flat=True))
    if not reminder_ids:
        return 0
    Task.objects.filter(id__in=reminder_ids).update(
        status=TaskStatus.CANCELLED,
        completed_at=None,
        updated_at=timezone.now(),
    )
    return len(reminder_ids)


def infer_starter_task_type(title):
    normalized = str(title or "").strip().lower()
    if "test" in normalized or "blood" in normalized or "urine" in normalized:
        return TaskType.LAB
    if "scan" in normalized or "injection" in normalized or "nst" in normalized:
        return TaskType.PROCEDURE
    return TaskType.VISIT


def _default_starter_anchor_for_workflow(workflow_key, *, applies_to=StarterTaskAppliesTo.ALWAYS):
    if workflow_key == "anc":
        return StarterTaskAnchor.LMP
    if workflow_key == "surgery":
        if applies_to == StarterTaskAppliesTo.SURVEILLANCE:
            return StarterTaskAnchor.REVIEW_DATE
        return StarterTaskAnchor.SURGERY_DATE
    return StarterTaskAnchor.REVIEW_DATE


def _default_starter_label_for_workflow(workflow_key, *, applies_to=StarterTaskAppliesTo.ALWAYS):
    if workflow_key == "anc":
        return "ANC"
    if workflow_key == "surgery":
        if applies_to == StarterTaskAppliesTo.SURVEILLANCE:
            return "Surveillance"
        if applies_to == StarterTaskAppliesTo.PLANNED_SURGERY:
            return "Planned surgery"
        return "Surgery"
    return "Review"


def normalize_starter_task_templates(templates, *, workflow_key):
    normalized_templates = []
    if not isinstance(templates, list):
        return normalized_templates

    valid_anchor_values = set(StarterTaskAnchor.values)
    valid_applies_to_values = set(StarterTaskAppliesTo.values)
    valid_task_type_values = set(TaskType.values)
    for raw_template in templates:
        if not isinstance(raw_template, dict):
            continue
        title = " ".join(str(raw_template.get("title") or "").split())
        if not title:
            continue
        applies_to = str(raw_template.get("applies_to") or StarterTaskAppliesTo.ALWAYS).strip().lower()
        if applies_to not in valid_applies_to_values:
            applies_to = StarterTaskAppliesTo.ALWAYS
        anchor = str(raw_template.get("anchor") or "").strip().lower()
        if anchor not in valid_anchor_values:
            anchor = _default_starter_anchor_for_workflow(workflow_key, applies_to=applies_to)
        task_type = str(raw_template.get("task_type") or "").strip().upper()
        if task_type not in valid_task_type_values:
            task_type = infer_starter_task_type(title)
        try:
            offset_days = int(raw_template.get("offset_days", 0) or 0)
        except (TypeError, ValueError):
            offset_days = 0
        frequency_label = " ".join(str(raw_template.get("frequency_label") or "").split())
        normalized_templates.append(
            {
                "title": title,
                "anchor": anchor,
                "offset_days": offset_days,
                "task_type": task_type,
                "frequency_label": frequency_label,
                "applies_to": applies_to,
            }
        )
    return normalized_templates


def default_starter_task_templates_for_category_name(name, predefined_actions=None):
    workflow_key = workflow_key_for_category_name(name)
    actions = list(predefined_actions or [])
    if workflow_key == "anc":
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
        return [
            {
                "title": title,
                "anchor": StarterTaskAnchor.LMP,
                "offset_days": (month - 1) * 28,
                "task_type": infer_starter_task_type(title),
                "frequency_label": f"ANC month {month}",
                "applies_to": StarterTaskAppliesTo.ALWAYS,
            }
            for month, titles in anc_schedule.items()
            for title in titles
        ]
    if workflow_key == "surgery":
        return [
            {
                "title": "Lab test",
                "anchor": StarterTaskAnchor.SURGERY_DATE,
                "offset_days": -7,
                "task_type": TaskType.LAB,
                "frequency_label": "Pre-op",
                "applies_to": StarterTaskAppliesTo.PLANNED_SURGERY,
            },
            {
                "title": "Xray",
                "anchor": StarterTaskAnchor.SURGERY_DATE,
                "offset_days": -7,
                "task_type": TaskType.PROCEDURE,
                "frequency_label": "Pre-op",
                "applies_to": StarterTaskAppliesTo.PLANNED_SURGERY,
            },
            {
                "title": "ECG",
                "anchor": StarterTaskAnchor.SURGERY_DATE,
                "offset_days": -7,
                "task_type": TaskType.PROCEDURE,
                "frequency_label": "Pre-op",
                "applies_to": StarterTaskAppliesTo.PLANNED_SURGERY,
            },
            {
                "title": "Inform Anesthetist",
                "anchor": StarterTaskAnchor.SURGERY_DATE,
                "offset_days": -5,
                "task_type": TaskType.CALL,
                "frequency_label": "Pre-op",
                "applies_to": StarterTaskAppliesTo.PLANNED_SURGERY,
            },
            {
                "title": "Surgery Date",
                "anchor": StarterTaskAnchor.SURGERY_DATE,
                "offset_days": 0,
                "task_type": TaskType.PROCEDURE,
                "frequency_label": "Planned surgery",
                "applies_to": StarterTaskAppliesTo.PLANNED_SURGERY,
            },
            {
                "title": "Surveillance Review",
                "anchor": StarterTaskAnchor.REVIEW_DATE,
                "offset_days": 0,
                "task_type": TaskType.VISIT,
                "frequency_label": "",
                "applies_to": StarterTaskAppliesTo.SURVEILLANCE,
            },
        ]

    action = actions[0] if actions else "Review by consultant"
    return [
        {
            "title": action,
            "anchor": StarterTaskAnchor.REVIEW_DATE,
            "offset_days": 0,
            "task_type": TaskType.CUSTOM,
            "frequency_label": "",
            "applies_to": StarterTaskAppliesTo.ALWAYS,
        }
    ]


def starter_task_templates_for_category(category):
    workflow_key = workflow_key_for_category_name(category.name)
    saved_templates = normalize_starter_task_templates(
        category.starter_task_templates or [],
        workflow_key=workflow_key,
    )
    if saved_templates:
        return saved_templates
    return default_starter_task_templates_for_category_name(category.name, category.predefined_actions)


def _starter_task_floor_date(case: Case, *, today=None):
    if workflow_key_for_case(case) == "anc":
        return None
    if getattr(case, "created_at", None):
        return timezone.localtime(case.created_at).date()
    return today or timezone.localdate()


def _starter_task_base_date(case, template, *, today):
    anchor = template["anchor"]
    if anchor == StarterTaskAnchor.LMP:
        return case.lmp or today
    if anchor == StarterTaskAnchor.EFFECTIVE_EDD:
        return case.effective_edd or today
    if anchor == StarterTaskAnchor.SURGERY_DATE:
        return case.surgery_date or today
    if anchor == StarterTaskAnchor.CREATED_DATE:
        return _starter_task_floor_date(case, today=today) or today

    if case.review_date:
        return case.review_date
    if case.review_frequency:
        return today + timedelta(days=frequency_to_days(case.review_frequency))
    return today + timedelta(days=30)


def _starter_task_frequency_label(case, template):
    label = str(template.get("frequency_label") or "").strip()
    if label:
        return label
    if template["anchor"] == StarterTaskAnchor.REVIEW_DATE:
        return case.get_review_frequency_display() or "Review"
    workflow_key = workflow_key_for_case(case)
    return _default_starter_label_for_workflow(workflow_key, applies_to=template["applies_to"])


def plan_default_tasks(case: Case):
    workflow_key = workflow_key_for_case(case)
    tasks = []
    today = timezone.localdate()
    task_floor_date = _starter_task_floor_date(case, today=today)
    templates = starter_task_templates_for_category(case.category)

    for template in templates:
        applies_to = template["applies_to"]
        if workflow_key == "surgery":
            if applies_to == StarterTaskAppliesTo.PLANNED_SURGERY and case.surgical_pathway != SurgicalPathway.PLANNED_SURGERY:
                continue
            if applies_to == StarterTaskAppliesTo.SURVEILLANCE and case.surgical_pathway == SurgicalPathway.PLANNED_SURGERY:
                continue

        due = _starter_task_base_date(case, template, today=today) + timedelta(days=template["offset_days"])
        if workflow_key == "anc" and case.effective_edd and due > case.effective_edd:
            due = case.effective_edd
        tasks.append(
            {
                "title": template["title"],
                "due_date": due,
                "task_type": template["task_type"],
                "frequency_label": _starter_task_frequency_label(case, template),
            }
        )

    if task_floor_date:
        for task in tasks:
            task["due_date"] = max(task["due_date"], task_floor_date)

    return tasks


def build_default_tasks(case: Case, actor):
    created = []
    for task_plan in plan_default_tasks(case):
        created.append(
            Task.objects.create(
                case=case,
                title=task_plan["title"],
                due_date=task_plan["due_date"],
                task_type=task_plan["task_type"],
                frequency_label=task_plan["frequency_label"],
                created_by=actor,
            )
        )
    return created


def create_quick_entry_details_task(case: Case, actor, due_date=None):
    return Task.objects.create(
        case=case,
        title=QUICK_ENTRY_DETAILS_TASK_TITLE,
        due_date=due_date or case.review_date or timezone.localdate(),
        task_type=TaskType.CUSTOM,
        frequency_label=QUICK_ENTRY_FREQUENCY_LABEL,
        created_by=actor,
    )
