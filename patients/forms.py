import json
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .models import (
    AncHighRiskReason,
    CallLog,
    Case,
    CaseActivityLog,
    DepartmentConfig,
    NonCommunicableDisease,
    RoleSetting,
    Task,
    TaskStatus,
    VitalEntry,
    ensure_default_departments,
    ensure_default_role_settings,
)


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


class DepartmentConfigForm(StyledModelForm):
    predefined_actions_text = forms.CharField(required=False, help_text="Comma-separated actions")
    metadata_template_text = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), help_text="JSON object")

    class Meta:
        model = DepartmentConfig
        fields = ["name", "auto_follow_up_days", "predefined_actions_text", "metadata_template_text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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



class UserRoleForm(forms.Form):
    def __init__(self, *args, **kwargs):
        ensure_default_role_settings()
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["user"] = forms.ModelChoiceField(queryset=User.objects.order_by("username"), widget=forms.Select(attrs={"class": "form-select"}))
        self.fields["role"] = forms.ModelChoiceField(queryset=Group.objects.order_by("name"), widget=forms.Select(attrs={"class": "form-select"}))
