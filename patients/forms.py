import json
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Q
from django.forms import modelformset_factory

from .models import (
    AncHighRiskReason,
    CallLog,
    Case,
    CaseActivityLog,
    DepartmentConfig,
    DeviceApprovalPolicy,
    PatientDataBackupSchedule,
    NonCommunicableDisease,
    RoleSetting,
    Task,
    TaskStatus,
    ThemeSettings,
    UserAdminNote,
    VitalEntry,
    ensure_default_departments,
    ensure_default_role_settings,
)
from .theme import (
    THEME_FORM_SECTIONS,
    field_name_to_css_var,
    flatten_theme_tokens,
    merge_theme_tokens,
    normalize_hex_color,
    theme_field_definitions,
    unflatten_theme_tokens,
)
from .database_bundle import IMPORT_CONFIRMATION_PHRASE


User = get_user_model()


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                css_class = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                css_class = "form-select"
            else:
                css_class = "form-control"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()


class CaseForm(StyledModelForm):
    ncd_flags = forms.MultipleChoiceField(
        required=False,
        choices=NonCommunicableDisease.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Non-Communicable Diseases",
    )
    anc_high_risk_reasons = forms.MultipleChoiceField(
        required=False,
        choices=AncHighRiskReason.choices,
        widget=forms.CheckboxSelectMultiple,
        label="ANC High-Risk Reasons",
    )

    def __init__(self, *args, **kwargs):
        ensure_default_departments()
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = self.fields["category"].queryset.order_by("name")
        if self.instance and self.instance.pk:
            self.fields["ncd_flags"].initial = self.instance.ncd_flags
            self.fields["anc_high_risk_reasons"].initial = self.instance.anc_high_risk_reasons

        gpla_choices = [("", "-")] + [(i, i) for i in range(1, 11)]
        for field_name in ["gravida", "para", "abortions", "living"]:
            self.fields[field_name].widget = forms.Select(choices=gpla_choices)

    def clean(self):
        cleaned_data = super().clean()
        dob = cleaned_data.get("date_of_birth")
        entered_age = cleaned_data.get("age")
        if dob:
            today = timezone.localdate()
            years = today.year - dob.year
            has_had_birthday = (today.month, today.day) >= (dob.month, dob.day)
            cleaned_data["age"] = years if has_had_birthday else years - 1
        elif entered_age is None:
            self.add_error("age", "Enter age when date of birth is not available.")

        category = cleaned_data.get("category")
        category_name = category.name.upper() if category else ""
        high_risk = cleaned_data.get("high_risk")
        anc_high_risk_reasons = cleaned_data.get("anc_high_risk_reasons", [])

        g, p, a, l = (
            cleaned_data.get("gravida"),
            cleaned_data.get("para"),
            cleaned_data.get("abortions"),
            cleaned_data.get("living"),
        )
        if category_name == "ANC" and None not in (g, p, a, l):
            if p > g:
                self.add_error("para", "P cannot exceed G.")
            if p + a > g:
                self.add_error("abortions", "P + A cannot exceed G.")
        if category_name == "ANC":
            rch_number = (cleaned_data.get("rch_number") or "").strip()
            if rch_number and not rch_number.isdigit():
                self.add_error("rch_number", "RCH number must contain digits only.")
            if not rch_number and not cleaned_data.get("rch_bypass"):
                self.add_error("rch_number", "Enter RCH number or bypass it for now.")
            if rch_number:
                cleaned_data["rch_bypass"] = False
            if high_risk and not anc_high_risk_reasons:
                self.add_error("anc_high_risk_reasons", "Select at least one ANC high-risk reason.")
        else:
            cleaned_data["anc_high_risk_reasons"] = []
            cleaned_data["rch_number"] = ""
            cleaned_data["rch_bypass"] = False

        if category_name == "ANC" and not high_risk:
            cleaned_data["anc_high_risk_reasons"] = []
        return cleaned_data

    def clean_ncd_flags(self):
        return self.cleaned_data.get("ncd_flags", [])

    def clean_anc_high_risk_reasons(self):
        return self.cleaned_data.get("anc_high_risk_reasons", [])

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.ncd_flags = self.cleaned_data.get("ncd_flags", [])
        instance.anc_high_risk_reasons = self.cleaned_data.get("anc_high_risk_reasons", [])
        if commit:
            instance.save()
        return instance

    class Meta:
        model = Case
        fields = [
            "uhid",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "place",
            "age",
            "phone_number",
            "alternate_phone_number",
            "category",
            "status",
            "diagnosis",
            "ncd_flags",
            "referred_by",
            "high_risk",
            "anc_high_risk_reasons",
            "rch_number",
            "rch_bypass",
            "lmp",
            "edd",
            "usg_edd",
            "surgical_pathway",
            "surgery_done",
            "surgery_date",
            "review_frequency",
            "review_date",
            "gravida",
            "para",
            "abortions",
            "living",
            "notes",
        ]
        widgets = {
            "lmp": forms.DateInput(attrs={"type": "date"}),
            "edd": forms.DateInput(attrs={"type": "date"}),
            "usg_edd": forms.DateInput(attrs={"type": "date"}),
            "surgery_date": forms.DateInput(attrs={"type": "date"}),
            "review_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }


class TaskForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if not instance or not instance.pk:
            return
        is_anc = instance.case and instance.case.category.name.upper() == "ANC"
        if is_anc and instance.due_date and instance.due_date > timezone.localdate():
            self.fields["status"].choices = [
                choice for choice in self.fields["status"].choices if choice[0] != TaskStatus.COMPLETED
            ]

    class Meta:
        model = Task
        fields = ["title", "due_date", "status", "assigned_user", "task_type", "frequency_label", "notes"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class VitalEntryForm(StyledModelForm):
    hb_warning_message = "Hemoglobin is outside expected ANC range (4.0 to 13.0). The value was saved."
    BP_PRESET_CHOICES = [
        ("", "Choose BP"),
        ("90/50", "90/50"),
        ("90/60", "90/60"),
        ("90/70", "90/70"),
        ("100/60", "100/60"),
        ("100/70", "100/70"),
        ("100/80", "100/80"),
        ("110/60", "110/60"),
        ("110/70", "110/70"),
        ("110/80", "110/80"),
        ("120/60", "120/60"),
        ("120/70", "120/70"),
        ("120/80", "120/80"),
        ("120/90", "120/90"),
        ("130/70", "130/70"),
        ("130/80", "130/80"),
        ("130/90", "130/90"),
        ("140/80", "140/80"),
        ("140/90", "140/90"),
        ("150/90", "150/90"),
        ("160/100", "160/100"),
    ]
    bp_preset = forms.ChoiceField(required=False, choices=BP_PRESET_CHOICES, label="BP")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hb_warning = False
        self.fields["recorded_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["bp_systolic"].widget = forms.HiddenInput()
        self.fields["bp_diastolic"].widget = forms.HiddenInput()
        self.fields["pr"].widget = forms.Select(choices=self._pr_choices())
        self.fields["spo2"].widget = forms.Select(choices=self._spo2_choices())
        self.fields["weight_kg"].widget = forms.Select(choices=self._weight_choices())
        if not self.is_bound:
            if self.instance and self.instance.pk and self.instance.recorded_at:
                local_recorded_at = timezone.localtime(self.instance.recorded_at)
            else:
                local_recorded_at = timezone.localtime(timezone.now())
            self.initial["recorded_at"] = local_recorded_at.strftime("%Y-%m-%dT%H:%M")
            if self.instance and self.instance.bp_systolic and self.instance.bp_diastolic:
                self.initial["bp_preset"] = f"{self.instance.bp_systolic}/{self.instance.bp_diastolic}"
            hemoglobin_value = getattr(self.instance, "hemoglobin", None)
            if hemoglobin_value is not None and (hemoglobin_value < Decimal("4.0") or hemoglobin_value > Decimal("13.0")):
                self.hb_warning = True

    @staticmethod
    def _pr_choices():
        return [("", "Choose PR")] + [(str(value), str(value)) for value in range(50, 131)]

    @staticmethod
    def _spo2_choices():
        return [("", "Choose SpO2")] + [(str(value), f"{value}%") for value in range(100, 89, -1)]

    @staticmethod
    def _weight_choices():
        options = [("", "Choose weight")]
        current = Decimal("30.0")
        while current <= Decimal("120.0"):
            options.append((str(current), f"{current}"))
            current += Decimal("0.5")
        return options

    def clean(self):
        cleaned_data = super().clean()
        bp_preset = cleaned_data.get("bp_preset") or ""
        if bp_preset:
            systolic, diastolic = bp_preset.split("/", 1)
            cleaned_data["bp_systolic"] = int(systolic)
            cleaned_data["bp_diastolic"] = int(diastolic)
        bp_systolic = cleaned_data.get("bp_systolic")
        bp_diastolic = cleaned_data.get("bp_diastolic")
        pr = cleaned_data.get("pr")
        spo2 = cleaned_data.get("spo2")
        weight_kg = cleaned_data.get("weight_kg")
        hemoglobin = cleaned_data.get("hemoglobin")

        if all(value in [None, ""] for value in [bp_systolic, bp_diastolic, pr, spo2, weight_kg, hemoglobin]):
            raise forms.ValidationError("Enter at least one vitals metric.")

        if (bp_systolic is None) ^ (bp_diastolic is None):
            if bp_systolic is None:
                self.add_error("bp_systolic", "Enter systolic BP when diastolic BP is provided.")
            if bp_diastolic is None:
                self.add_error("bp_diastolic", "Enter diastolic BP when systolic BP is provided.")

        if hemoglobin is not None and (hemoglobin < Decimal("4.0") or hemoglobin > Decimal("13.0")):
            self.hb_warning = True
        return cleaned_data

    def clean_hemoglobin(self):
        value = self.cleaned_data.get("hemoglobin")
        if value is None:
            return value
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError):
            return value

    class Meta:
        model = VitalEntry
        fields = ["recorded_at", "bp_systolic", "bp_diastolic", "pr", "spo2", "weight_kg", "hemoglobin"]
        widgets = {
            "recorded_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "hemoglobin": forms.NumberInput(attrs={"step": "0.1"}),
        }


class ActivityLogForm(StyledModelForm):
    class Meta:
        model = CaseActivityLog
        fields = ["note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 2, "placeholder": "Add follow-up note"}),
        }


class CallLogForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["task"].required = True
        self.fields["task"].empty_label = "Select associated task"
        self.fields["task"].error_messages["required"] = "Please select the associated task."

    class Meta:
        model = CallLog
        fields = ["task", "outcome", "notes"]
        widgets = {
            "task": forms.Select(),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional call note"}),
        }



class RecentCaseUpdateForm(StyledModelForm):
    class Meta:
        model = Case
        fields = ["diagnosis", "notes"]
        widgets = {
            "diagnosis": forms.TextInput(attrs={"placeholder": "Enter diagnosis"}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Add case notes"}),
        }


class RoleSettingForm(StyledModelForm):
    class Meta:
        model = RoleSetting
        fields = [
            "role_name",
            "can_case_create",
            "can_case_edit",
            "can_task_create",
            "can_task_edit",
            "can_note_add",
            "can_manage_settings",
        ]
        widgets = {
            "can_case_create": forms.CheckboxInput(),
            "can_case_edit": forms.CheckboxInput(),
            "can_task_create": forms.CheckboxInput(),
            "can_task_edit": forms.CheckboxInput(),
            "can_note_add": forms.CheckboxInput(),
            "can_manage_settings": forms.CheckboxInput(),
        }


class RoleSettingUpdateForm(RoleSettingForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role_name"].disabled = True
        self.fields["role_name"].help_text = "Use Create Role for new names. Editing here updates permissions only."


class DepartmentConfigForm(StyledModelForm):
    predefined_actions_text = forms.CharField(required=False, help_text="Comma-separated actions")
    metadata_template_text = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), help_text="JSON object")

    class Meta:
        model = DepartmentConfig
        fields = ["name", "auto_follow_up_days", "predefined_actions_text", "metadata_template_text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["auto_follow_up_days"].help_text = (
            "Retained for future workflow defaults. Changing this does not alter live task generation today."
        )
        if self.instance.pk:
            self.fields["predefined_actions_text"].initial = ", ".join(self.instance.predefined_actions or [])
            self.fields["metadata_template_text"].initial = json.dumps(self.instance.metadata_template or {})

    def clean_metadata_template_text(self):
        raw = self.cleaned_data.get("metadata_template_text", "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise forms.ValidationError("Metadata template must be a JSON object.")
            return parsed
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc}")

    def save(self, commit=True):
        instance = super().save(commit=False)
        actions_raw = self.cleaned_data.get("predefined_actions_text", "")
        instance.predefined_actions = [a.strip() for a in actions_raw.split(",") if a.strip()]
        instance.metadata_template = self.cleaned_data.get("metadata_template_text", {})
        if commit:
            instance.save()
        return instance


class ThemeSettingsForm(forms.Form):
    section_definitions = THEME_FORM_SECTIONS

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance or ThemeSettings.get_solo()
        super().__init__(*args, **kwargs)
        initial_tokens = flatten_theme_tokens(merge_theme_tokens(self.instance.tokens))
        if not self.is_bound:
            self.initial.update(initial_tokens)

        self.sections = []
        for section in self.section_definitions:
            section_rows = []
            for row in section["rows"]:
                section_fields = []
                for field in row["fields"]:
                    field_name = field["name"]
                    self.fields[field_name] = forms.CharField(
                        label=field["label"],
                        max_length=7,
                        initial=initial_tokens[field_name],
                    )
                    self.fields[field_name].widget.attrs.update(
                        {
                            "class": "form-control theme-hex-input",
                            "maxlength": "7",
                            "pattern": "^#[0-9a-fA-F]{6}$",
                            "data-preview-var": field_name_to_css_var(field_name),
                        }
                    )
                    section_fields.append(
                        {
                            "name": field_name,
                            "label": field["label"],
                            "preview_var": field_name_to_css_var(field_name),
                            "bound_field": self[field_name],
                        }
                    )
                section_rows.append({"label": row["label"], "fields": section_fields})
            self.sections.append({"title": section["title"], "rows": section_rows})

    def clean(self):
        cleaned_data = super().clean()
        for field_name in theme_field_definitions():
            try:
                cleaned_data[field_name] = normalize_hex_color(cleaned_data[field_name])
            except (KeyError, ValueError) as exc:
                self.add_error(field_name, str(exc))
        return cleaned_data

    def save(self):
        self.instance.tokens = unflatten_theme_tokens(
            {field_name: self.cleaned_data[field_name] for field_name in theme_field_definitions()}
        )
        self.instance.save()
        return self.instance


class DepartmentThemeForm(forms.ModelForm):
    class Meta:
        model = DepartmentConfig
        fields = ["theme_bg_color", "theme_text_color"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        preview_id = f"theme-category-{self.instance.pk or 'new'}-preview"
        for field_name, role_label in (("theme_bg_color", "bg"), ("theme_text_color", "text")):
            self.fields[field_name].widget.attrs.update(
                {
                    "class": "form-control theme-hex-input",
                    "maxlength": "7",
                    "pattern": "^#[0-9a-fA-F]{6}$",
                    "data-category-preview": preview_id,
                    "data-category-role": role_label,
                }
            )

    def clean_theme_bg_color(self):
        return normalize_hex_color(self.cleaned_data["theme_bg_color"])

    def clean_theme_text_color(self):
        return normalize_hex_color(self.cleaned_data["theme_text_color"])


DepartmentThemeFormSet = modelformset_factory(
    DepartmentConfig,
    form=DepartmentThemeForm,
    extra=0,
)


class SeedMockDataForm(forms.Form):
    profile = forms.ChoiceField(choices=[("smoke", "Smoke (12 cases)"), ("full", "Full (30 cases)")], initial="full")
    count = forms.IntegerField(min_value=1, required=False, help_text="Optional override for case count.")
    include_vitals = forms.BooleanField(required=False, initial=False)
    include_rch_scenarios = forms.BooleanField(required=False, initial=False)
    reset_all = forms.BooleanField(required=False, initial=False, help_text="Delete all case/call/activity data before seeding.")
    confirm_reset_all = forms.BooleanField(required=False, initial=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profile"].widget.attrs["class"] = "form-select"
        self.fields["count"].widget.attrs["class"] = "form-control"
        for field_name in ["include_vitals", "include_rch_scenarios", "reset_all"]:
            self.fields[field_name].widget.attrs["class"] = "form-check-input"


class DatabaseImportForm(forms.Form):
    bundle_file = forms.FileField(help_text="Upload a MEDTRACK patient-data backup ZIP.")
    confirm_phrase = forms.CharField(
        label="Confirmation",
        help_text=f'Type "{IMPORT_CONFIRMATION_PHRASE}" to replace all patient records.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bundle_file"].widget.attrs["class"] = "form-control"
        self.fields["confirm_phrase"].widget.attrs["class"] = "form-control"
        self.fields["confirm_phrase"].widget.attrs["autocomplete"] = "off"

    def clean_bundle_file(self):
        bundle_file = self.cleaned_data["bundle_file"]
        if not bundle_file.name.lower().endswith(".zip"):
            raise forms.ValidationError("Upload a ZIP archive created by MEDTRACK.")
        return bundle_file

    def clean_confirm_phrase(self):
        confirm_phrase = (self.cleaned_data.get("confirm_phrase") or "").strip()
        if confirm_phrase != IMPORT_CONFIRMATION_PHRASE:
            raise forms.ValidationError(f'Type "{IMPORT_CONFIRMATION_PHRASE}" exactly to continue.')
        return confirm_phrase


class PatientDataBackupScheduleForm(forms.ModelForm):
    class Meta:
        model = PatientDataBackupSchedule
        fields = ["enabled", "daily_time"]
        widgets = {
            "enabled": forms.CheckboxInput(),
            "daily_time": forms.TimeInput(format="%H:%M", attrs={"type": "time", "step": 60}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["enabled"].widget.attrs["class"] = "form-check-input"
        self.fields["daily_time"].widget.attrs["class"] = "form-control"
        self.fields["daily_time"].input_formats = ["%H:%M", "%H:%M:%S"]
        self.fields["daily_time"].label = "Daily backup time"
        self.fields["daily_time"].help_text = (
            "Daily backups run at this time. Monthly backups run automatically on the 1st at 12:00 AM, "
            "and yearly backups run automatically on Jan 1 at 12:00 AM."
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("enabled") and not cleaned_data.get("daily_time") and "daily_time" not in self.errors:
            self.add_error("daily_time", "Choose the daily backup time.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.schedule_mode = "DAILY"
        instance.custom_times = []
        instance.retention_count = instance.DAILY_RETENTION_COUNT
        if commit:
            instance.save()
        return instance


class DeviceApprovalPolicyForm(forms.ModelForm):
    target_users = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 10}),
        help_text="Only selected users will require approved devices during the pilot.",
    )

    class Meta:
        model = DeviceApprovalPolicy
        fields = ["enabled", "target_users"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["enabled"].widget.attrs["class"] = "form-check-input"
        self.fields["target_users"].queryset = User.objects.order_by("username")


class UserManagementBaseForm(StyledModelForm):
    role = forms.ModelChoiceField(queryset=Group.objects.none(), label="Primary role")
    temporary_password_note = forms.CharField(
        required=False,
        label="Temporary password note",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Admin-only plaintext note for short-lived password handoff. Clear it once it is no longer needed.",
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "is_active"]

    def __init__(self, *args, **kwargs):
        ensure_default_role_settings()
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Group.objects.order_by("name")
        self.fields["role"].empty_label = "Select role"
        self.fields["role"].help_text = (
            "Saving replaces any existing group memberships with one primary role, matching current app behavior."
        )
        self.fields["username"].help_text = "Used for sign-in."
        if self.instance and self.instance.pk:
            primary_group = self.instance.groups.order_by("name").first()
            if primary_group:
                self.fields["role"].initial = primary_group
            note = getattr(self.instance, "admin_note", None)
            if note is not None:
                self.fields["temporary_password_note"].initial = note.temporary_password_note

    def _save_temporary_password_note(self, *, user, actor=None):
        note_text = (self.cleaned_data.get("temporary_password_note") or "").strip()
        note = getattr(user, "admin_note", None)
        actor_id = actor.pk if actor is not None else None
        if note is None and not note_text:
            return None
        if note is not None and note.temporary_password_note == note_text and note.updated_by_id == actor_id:
            return note
        if note is None:
            note = UserAdminNote(user=user)
        note.temporary_password_note = note_text
        note.updated_by = actor
        note.save()
        user.admin_note = note
        return note


class UserManagementCreateForm(UserManagementBaseForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned_data

    def save(self, commit=True, actor=None):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            user.groups.set([self.cleaned_data["role"]])
            self._save_temporary_password_note(user=user, actor=actor)
        return user


class UserManagementUpdateForm(UserManagementBaseForm):
    password1 = forms.CharField(
        label="New password",
        required=False,
        help_text="Leave blank to keep the current password.",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm new password",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def _current_manage_settings_access(self):
        if not self.instance.is_active:
            return False
        if self.instance.is_superuser:
            return True
        return RoleSetting.objects.filter(
            role_name__in=self.instance.groups.values_list("name", flat=True),
            can_manage_settings=True,
        ).exists()

    def _future_manage_settings_access(self, role, is_active):
        if not is_active:
            return False
        if self.instance.is_superuser:
            return True
        if not role:
            return False
        return RoleSetting.objects.filter(role_name=role.name, can_manage_settings=True).exists()

    def _other_active_settings_admin_exists(self):
        manage_settings_roles = RoleSetting.objects.filter(can_manage_settings=True).values_list("role_name", flat=True)
        return User.objects.filter(is_active=True).exclude(pk=self.instance.pk).filter(
            Q(is_superuser=True) | Q(groups__name__in=manage_settings_roles)
        ).distinct().exists()

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "Passwords do not match.")

        role = cleaned_data.get("role")
        is_active = cleaned_data.get("is_active")
        if (
            self.instance
            and self.instance.pk
            and self._current_manage_settings_access()
            and not self._future_manage_settings_access(role, is_active)
            and not self._other_active_settings_admin_exists()
        ):
            message = "Keep at least one active admin user with settings access."
            if is_active:
                self.add_error("role", message)
            else:
                self.add_error("is_active", message)
        return cleaned_data

    def save(self, commit=True, actor=None):
        user = super().save(commit=False)
        password1 = self.cleaned_data.get("password1")
        if password1:
            user.set_password(password1)
        if commit:
            user.save()
            user.groups.set([self.cleaned_data["role"]])
            self._save_temporary_password_note(user=user, actor=actor)
        return user


class UserRoleForm(forms.Form):
    def __init__(self, *args, **kwargs):
        ensure_default_role_settings()
        super().__init__(*args, **kwargs)
        self.fields["user"] = forms.ModelChoiceField(queryset=User.objects.order_by("username"), widget=forms.Select(attrs={"class": "form-select"}))
        self.fields["role"] = forms.ModelChoiceField(queryset=Group.objects.order_by("name"), widget=forms.Select(attrs={"class": "form-select"}))
