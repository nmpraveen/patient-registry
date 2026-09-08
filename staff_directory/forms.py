from django import forms
from django.forms import formset_factory
from rest_framework.exceptions import ValidationError

from .models import Contact
from .serializers import PhoneSerializer


class ContactForm(forms.ModelForm):
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput, initial=1)

    class Meta:
        model = Contact
        fields = ("name", "role_specialty", "organization", "notes", "is_active")
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class PhoneForm(forms.Form):
    label = forms.CharField(max_length=40, required=False)
    number = forms.CharField(max_length=32)
    extension = forms.CharField(max_length=10, required=False)

    def clean(self):
        values = super().clean()
        if self.errors or not values or values.get("DELETE"):
            return values
        serializer = PhoneSerializer(data=values)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            raise forms.ValidationError(str(exc.detail))
        return values


PhoneFormSet = formset_factory(PhoneForm, extra=0, can_delete=True, max_num=10,
                               validate_max=True, min_num=1, validate_min=True, absolute_max=10)
