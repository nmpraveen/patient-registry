from django import forms

from .models import Announcement


class AnnouncementForm(forms.ModelForm):
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput, initial=1)

    class Meta:
        model = Announcement
        fields = ("text", "priority", "audience", "audience_roles", "starts_at", "ends_at", "is_active")
        widgets = {
            "text": forms.Textarea(attrs={"rows": 4}),
            "starts_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        }

    def clean(self):
        data = super().clean()
        if data.get("audience") == Announcement.Audience.SELECTED_ROLES and not data.get("audience_roles"):
            self.add_error("audience_roles", "Select at least one role.")
        if data.get("audience") == Announcement.Audience.ALL_STAFF:
            data["audience_roles"] = []
        if data.get("starts_at") and data.get("ends_at") and data["ends_at"] <= data["starts_at"]:
            self.add_error("ends_at", "Expiry must follow the start.")
        return data
