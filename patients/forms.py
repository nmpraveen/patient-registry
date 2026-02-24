from django import forms

from .models import Case, CaseActivityLog, Task


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()


class CaseForm(StyledModelForm):
    class Meta:
        model = Case
        fields = [
            "uhid",
            "patient_name",
            "phone_number",
            "category",
            "status",
            "lmp",
            "edd",
            "surgical_pathway",
            "surgery_done",
            "surgery_date",
            "review_frequency",
            "review_date",
            "notes",
        ]
        widgets = {
            "lmp": forms.DateInput(attrs={"type": "date"}),
            "edd": forms.DateInput(attrs={"type": "date"}),
            "surgery_date": forms.DateInput(attrs={"type": "date"}),
            "review_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class TaskForm(StyledModelForm):
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
        fields = ["task", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 2, "placeholder": "Add follow-up note"}),
        }
