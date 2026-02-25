import json

from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .models import (
    Case,
    CaseActivityLog,
    DepartmentConfig,
    NonCommunicableDisease,
    RoleSetting,
    Task,
    TaskStatus,
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

    def __init__(self, *args, **kwargs):
        ensure_default_departments()
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = self.fields["category"].queryset.order_by("name")
        if self.instance and self.instance.pk:
            self.fields["ncd_flags"].initial = self.instance.ncd_flags

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
        return cleaned_data

    def clean_ncd_flags(self):
        return self.cleaned_data.get("ncd_flags", [])

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.ncd_flags = self.cleaned_data.get("ncd_flags", [])
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


class ActivityLogForm(StyledModelForm):
    class Meta:
        model = CaseActivityLog
        fields = ["note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 2, "placeholder": "Add follow-up note"}),
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


class UserRoleForm(forms.Form):
    def __init__(self, *args, **kwargs):
        ensure_default_role_settings()
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["user"] = forms.ModelChoiceField(queryset=User.objects.order_by("username"), widget=forms.Select(attrs={"class": "form-select"}))
        self.fields["role"] = forms.ModelChoiceField(queryset=Group.objects.order_by("name"), widget=forms.Select(attrs={"class": "form-select"}))
