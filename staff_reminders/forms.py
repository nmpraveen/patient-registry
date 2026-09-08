from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import Reminder
from .policy import assignees


class ReminderForm(forms.Form):
    title = forms.CharField(max_length=200)
    assignee = forms.ModelChoiceField(queryset=None)
    due_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    advance_notice_days = forms.IntegerField(min_value=0, max_value=365, initial=0)
    recurrence = forms.ChoiceField(choices=Reminder.Recurrence.choices)
    is_active = forms.BooleanField(required=False, initial=True)
    version = forms.IntegerField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, reminder=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.reminder = reminder
        self.fields["assignee"].queryset = assignees()
        if reminder:
            self.fields["assignee"].queryset = get_user_model().objects.filter(
                Q(pk__in=assignees().values("pk")) | Q(pk=reminder.assignee_id)
            ).order_by("username", "pk")
            self.initial.update({"title": reminder.title, "assignee": reminder.assignee_id,
                                 "due_date": reminder.due_date, "advance_notice_days": reminder.advance_notice_days,
                                 "recurrence": reminder.recurrence, "is_active": reminder.is_active, "version": reminder.version})
            self.fields["due_date"].disabled = True
            self.fields["recurrence"].disabled = True
            self.fields["version"].required = True
        else:
            del self.fields["is_active"]
        for field in self.fields.values():
            if not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs["class"] = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"

    def values(self):
        data = self.cleaned_data
        values = {"title": data["title"], "assignee_id": data["assignee"].pk,
                  "advance_notice_days": data["advance_notice_days"]}
        if self.reminder:
            if values["assignee_id"] == self.reminder.assignee_id:
                del values["assignee_id"]
            values["is_active"] = data["is_active"]
        else:
            values.update(due_date=data["due_date"], recurrence=data["recurrence"])
        return values
