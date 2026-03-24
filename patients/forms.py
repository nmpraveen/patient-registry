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
    case_subcategory_choices_for_category_name,
    case_subcategory_group_for_category_name,
    CaseActivityLog,
    CasePrefix,
    CaseStatus,
    DepartmentConfig,
    DeviceApprovalPolicy,
    Gender,
    generate_quick_entry_uhid,
    generate_temporary_patient_uhid,
    Patient,
    PatientDataBackupSchedule,
    NonCommunicableDisease,
    RoleSetting,
    Task,
    TaskStatus,
    ThemeSettings,
    UserAdminNote,
    valid_case_subcategory_values_for_category_name,
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

DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d/%m/%Y"]
CRAYONS_DATEPICKER_ATTRS = {
    "type": "date",
    "data-crayons-datepicker": "true",
    "data-crayons-datepicker-format": "dd/MM/yyyy",
    "data-crayons-datepicker-locale": "en-IN",
    "data-crayons-datepicker-placeholder": "dd/mm/yyyy",
    "data-crayons-datepicker-show-footer": "false",
}


CASE_PREFIX_SELECT_CHOICES = [("", "Select prefix"), *list(CasePrefix.choices)]
PATIENT_MODE_CHOICES = [("new", "New patient"), ("existing", "Existing patient")]


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


class PatientForm(StyledModelForm):
    use_temporary_patient_id = forms.BooleanField(
        required=False,
        label="Use temporary ID for now",
        help_text="Create a temporary local patient ID and merge it later when the real UHID is known.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["prefix"].required = True
        self.fields["prefix"].label = "Prefix"
        self.fields["prefix"].choices = CASE_PREFIX_SELECT_CHOICES
        self.fields["uhid"].label = "UHID"
        self.fields["date_of_birth"].input_formats = DATE_INPUT_FORMATS
        if self.instance and self.instance.pk:
            self.fields["use_temporary_patient_id"].initial = self.instance.is_temporary_id

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

        use_temporary_patient_id = cleaned_data.get("use_temporary_patient_id")
        uhid = (cleaned_data.get("uhid") or "").strip()
        if use_temporary_patient_id:
            if self.instance.pk and self.instance.is_temporary_id and self.instance.uhid:
                cleaned_data["uhid"] = self.instance.uhid
            else:
                cleaned_data["uhid"] = generate_temporary_patient_uhid()
        elif not uhid:
            self.add_error("uhid", "Enter UHID or use a temporary ID.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.is_temporary_id = bool(self.cleaned_data.get("use_temporary_patient_id"))
        if commit:
            instance.save()
        return instance

    class Meta:
        model = Patient
        fields = [
            "uhid",
            "prefix",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "place",
            "age",
            "phone_number",
            "alternate_phone_number",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs=dict(CRAYONS_DATEPICKER_ATTRS)),
        }


def _selected_category_from_form(form):
    category = form.data.get("category") if form.is_bound else None
    if not category:
        category = form.initial.get("category")
    if not category and getattr(form.instance, "category_id", None):
        return form.instance.category
    if isinstance(category, DepartmentConfig):
        return category
    if category in ("", None):
        return None
    try:
        return DepartmentConfig.objects.only("id", "name").get(pk=category)
    except (DepartmentConfig.DoesNotExist, TypeError, ValueError):
        return None


def _case_subcategory_help_text(*, subcategory_group, optional_copy, has_options):
    if not has_options:
        return ""
    if optional_copy:
        if subcategory_group == "surgery":
            return "Optional for quick entry. Choose the surgical specialty if known."
        if subcategory_group == "medicine":
            return "Optional for quick entry. Choose the medical specialty if known."
        return "Optional for quick entry. Choose a subcategory if known."
    if subcategory_group == "surgery":
        return "Choose the surgical specialty."
    if subcategory_group == "medicine":
        return "Choose the medical specialty."
    return "Choose a subcategory."


def _configure_case_subcategory_field(field, *, category, required, optional_copy=False):
    category_name = category.name if category else ""
    subcategory_group = case_subcategory_group_for_category_name(category_name)
    subcategory_choices = list(case_subcategory_choices_for_category_name(category_name))
    if subcategory_choices:
        placeholder = "Optional subcategory" if optional_copy else "Select subcategory"
    else:
        placeholder = "Select category first"
    field.label = "Subcategory"
    field.required = required and bool(subcategory_choices)
    field.choices = [("", placeholder)] + subcategory_choices
    field.help_text = _case_subcategory_help_text(
        subcategory_group=subcategory_group,
        optional_copy=optional_copy,
        has_options=bool(subcategory_choices),
    )
    field.widget.attrs["autocomplete"] = "off"
    field.widget.attrs["data-subcategory-group"] = subcategory_group
    if subcategory_choices:
        field.widget.attrs.pop("disabled", None)
    else:
        field.widget.attrs["disabled"] = "disabled"


class CaseForm(StyledModelForm):
    patient_mode = forms.ChoiceField(
        choices=PATIENT_MODE_CHOICES,
        widget=forms.RadioSelect(),
        initial="new",
        label="Patient source",
        required=False,
    )
    selected_patient = forms.ModelChoiceField(
        queryset=Patient.objects.none(),
        required=False,
        widget=forms.HiddenInput(),
    )
    use_temporary_uhid = forms.BooleanField(required=False, label="Use temporary patient ID")
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
        self._generated_temporary_uhid = ""
        self.fields["selected_patient"].queryset = Patient.objects.filter(merged_into__isnull=True).order_by(
            "patient_name", "uhid"
        )
        self.fields["prefix"].required = False
        self.fields["first_name"].required = False
        self.fields["last_name"].required = False
        self.fields["phone_number"].required = False
        self.fields["prefix"].label = "Prefix"
        self.fields["prefix"].choices = CASE_PREFIX_SELECT_CHOICES
        self.fields["category"].queryset = self.fields["category"].queryset.order_by("name")
        self.fields["category"].widget = forms.RadioSelect()
        self.fields["category"].empty_label = None
        self.fields["category"].widget.choices = self.fields["category"].choices
        self._configure_subcategory_field()
        self.fields["uhid"].label = "UHID"
        self.fields["selected_patient"].label = "Selected patient"
        self.fields["use_temporary_uhid"].help_text = "Use a local temporary patient ID when the real UHID is not known yet."
        self.fields["rch_number"].label = "RCH number"
        self.fields["rch_bypass"].label = "RCH bypass"
        self.fields["lmp"].label = "LMP"
        self.fields["edd"].label = "EDD"
        self.fields["usg_edd"].label = "USG EDD"
        for field_name in ["date_of_birth", "lmp", "edd", "usg_edd", "surgery_date", "review_date"]:
            self.fields[field_name].input_formats = DATE_INPUT_FORMATS
        patient = getattr(self.instance, "patient", None) if self.instance and self.instance.pk else None
        if patient:
            self.initial.setdefault("selected_patient", patient.pk)
            self.initial.setdefault("patient_mode", "existing")
            self.initial.setdefault("uhid", patient.uhid)
            self.initial.setdefault("prefix", patient.prefix)
            self.initial.setdefault("first_name", patient.first_name)
            self.initial.setdefault("last_name", patient.last_name)
            self.initial.setdefault("gender", patient.gender)
            self.initial.setdefault("date_of_birth", patient.date_of_birth)
            self.initial.setdefault("place", patient.place)
            self.initial.setdefault("age", patient.age)
            self.initial.setdefault("phone_number", patient.phone_number)
            self.initial.setdefault("alternate_phone_number", patient.alternate_phone_number)
            self.initial.setdefault("use_temporary_uhid", patient.is_temporary_id)
        if self.instance and self.instance.pk:
            self.fields["ncd_flags"].initial = self.instance.ncd_flags
            self.fields["anc_high_risk_reasons"].initial = self.instance.anc_high_risk_reasons
            self.fields["patient_mode"].widget = forms.HiddenInput()
            self.fields["selected_patient"].widget = forms.HiddenInput()
        else:
            self.fields["status"].widget = forms.HiddenInput()
            self.fields["status"].required = False
            self.initial.setdefault("status", CaseStatus.ACTIVE)
            self.initial.setdefault("patient_mode", "new")

        gpla_choices = [("", "-")] + [(i, i) for i in range(0, 11)]
        for field_name in ["gravida", "para", "abortions", "living", "ftnd", "lscs"]:
            self.fields[field_name].widget = forms.Select(choices=gpla_choices)

    def _selected_category_for_subcategory(self):
        return _selected_category_from_form(self)

    def _configure_subcategory_field(self):
        _configure_case_subcategory_field(
            self.fields["subcategory"],
            category=self._selected_category_for_subcategory(),
            required=True,
            optional_copy=False,
        )

    def _build_patient_candidate(self, cleaned_data):
        patient = getattr(self.instance, "patient", None) if self.instance and self.instance.pk else None
        if patient is None:
            patient = Patient()
        patient.uhid = (cleaned_data.get("uhid") or "").strip()
        patient.prefix = cleaned_data.get("prefix") or ""
        patient.first_name = cleaned_data.get("first_name") or ""
        patient.last_name = cleaned_data.get("last_name") or ""
        patient.gender = cleaned_data.get("gender") or ""
        patient.date_of_birth = cleaned_data.get("date_of_birth")
        patient.place = cleaned_data.get("place") or ""
        patient.age = cleaned_data.get("age")
        patient.phone_number = (cleaned_data.get("phone_number") or "").strip()
        patient.alternate_phone_number = (cleaned_data.get("alternate_phone_number") or "").strip()
        patient.is_temporary_id = bool(cleaned_data.get("use_temporary_uhid"))
        if self.instance and self.instance.pk:
            patient.created_by = getattr(self.instance.patient, "created_by", None)
            patient.merged_into = getattr(self.instance.patient, "merged_into", None)
        return patient

    @staticmethod
    def _sync_patient_candidate_from_cleaned_data(patient, cleaned_data):
        patient.uhid = (cleaned_data.get("uhid") or "").strip()
        patient.prefix = cleaned_data.get("prefix") or ""
        patient.first_name = cleaned_data.get("first_name") or ""
        patient.last_name = cleaned_data.get("last_name") or ""
        patient.gender = cleaned_data.get("gender") or ""
        patient.date_of_birth = cleaned_data.get("date_of_birth")
        patient.place = cleaned_data.get("place") or ""
        patient.age = cleaned_data.get("age")
        patient.phone_number = (cleaned_data.get("phone_number") or "").strip()
        patient.alternate_phone_number = (cleaned_data.get("alternate_phone_number") or "").strip()
        patient.is_temporary_id = bool(cleaned_data.get("use_temporary_uhid"))

    def clean(self):
        cleaned_data = super().clean()
        patient_mode = cleaned_data.get("patient_mode") or ("existing" if self.instance.pk else "new")
        cleaned_data["patient_mode"] = patient_mode
        selected_patient = cleaned_data.get("selected_patient")
        if patient_mode == "existing" and not selected_patient and not self.instance.pk:
            self.add_error("selected_patient", "Choose an existing patient before saving the case.")

        if patient_mode == "existing" and selected_patient and not self.instance.pk:
            cleaned_data["uhid"] = selected_patient.uhid
            cleaned_data["prefix"] = selected_patient.prefix
            cleaned_data["first_name"] = selected_patient.first_name
            cleaned_data["last_name"] = selected_patient.last_name
            cleaned_data["gender"] = selected_patient.gender
            cleaned_data["date_of_birth"] = selected_patient.date_of_birth
            cleaned_data["place"] = selected_patient.place
            cleaned_data["age"] = selected_patient.age
            cleaned_data["phone_number"] = selected_patient.phone_number
            cleaned_data["alternate_phone_number"] = selected_patient.alternate_phone_number
            cleaned_data["use_temporary_uhid"] = selected_patient.is_temporary_id
            cleaned_data["patient_instance"] = selected_patient
        else:
            if cleaned_data.get("use_temporary_uhid"):
                if not self._generated_temporary_uhid:
                    self._generated_temporary_uhid = generate_temporary_patient_uhid()
                cleaned_data["uhid"] = self._generated_temporary_uhid
            elif not (cleaned_data.get("uhid") or "").strip():
                self.add_error("uhid", "Enter UHID or enable a temporary patient ID.")

            missing_patient_fields = []
            if not cleaned_data.get("prefix"):
                self.add_error("prefix", "This field is required.")
            for field_name in ["first_name", "last_name", "phone_number"]:
                if not (cleaned_data.get(field_name) or "").strip():
                    self.add_error(field_name, "This field is required.")
                    missing_patient_fields.append(field_name)

            patient_candidate = self._build_patient_candidate(cleaned_data)
            try:
                patient_candidate.full_clean(exclude=["created_by", "merged_into", *missing_patient_fields])
            except forms.ValidationError as exc:
                for field_name, errors in exc.message_dict.items():
                    target_field = field_name if field_name in self.fields else None
                    for error in errors:
                        self.add_error(target_field, error)
            cleaned_data["patient_instance"] = patient_candidate

        dob = cleaned_data.get("date_of_birth")
        entered_age = cleaned_data.get("age")
        if dob:
            today = timezone.localdate()
            years = today.year - dob.year
            has_had_birthday = (today.month, today.day) >= (dob.month, dob.day)
            cleaned_data["age"] = years if has_had_birthday else years - 1
        elif entered_age is None:
            self.add_error("age", "Enter age when date of birth is not available.")

        if not self.instance.pk and not cleaned_data.get("status"):
            cleaned_data["status"] = CaseStatus.ACTIVE

        category = cleaned_data.get("category")
        category_name = category.name.upper() if category else ""
        valid_subcategories = valid_case_subcategory_values_for_category_name(category_name)
        if not valid_subcategories:
            cleaned_data["subcategory"] = ""
        high_risk = cleaned_data.get("high_risk")
        anc_high_risk_reasons = cleaned_data.get("anc_high_risk_reasons", [])

        g, p, a, l = (
            cleaned_data.get("gravida"),
            cleaned_data.get("para"),
            cleaned_data.get("abortions"),
            cleaned_data.get("living"),
        )
        ftnd = cleaned_data.get("ftnd") or 0
        lscs = cleaned_data.get("lscs") or 0
        is_primi_selection = (g, p, a, l) == (1, 0, 0, 0)
        if category_name == "ANC" and None not in (g, p, a, l):
            if p > g:
                self.add_error("para", "P cannot exceed G.")
            if p + a > g:
                self.add_error("abortions", "P + A cannot exceed G.")
        if category_name == "ANC":
            if not p or is_primi_selection:
                cleaned_data["ftnd"] = 0
                cleaned_data["lscs"] = 0
                ftnd = 0
                lscs = 0
            elif ftnd + lscs > p:
                cleaned_data["ftnd"] = 0
                cleaned_data["lscs"] = 0
                ftnd = 0
                lscs = 0
            if p and not is_primi_selection and ftnd + lscs != p:
                self.add_error("ftnd", "FTND and LSCS together must equal Para.")
                self.add_error("lscs", "FTND and LSCS together must equal Para.")
        if category_name == "ANC":
            cleaned_data["gender"] = cleaned_data.get("gender") or Gender.FEMALE
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
            cleaned_data["ftnd"] = 0
            cleaned_data["lscs"] = 0

        if category_name == "ANC" and not high_risk:
            cleaned_data["anc_high_risk_reasons"] = []

        patient_candidate = cleaned_data.get("patient_instance")
        if isinstance(patient_candidate, Patient) and (self.instance.pk or patient_mode != "existing"):
            self._sync_patient_candidate_from_cleaned_data(patient_candidate, cleaned_data)
        return cleaned_data

    def clean_ncd_flags(self):
        return self.cleaned_data.get("ncd_flags", [])

    def clean_anc_high_risk_reasons(self):
        return self.cleaned_data.get("anc_high_risk_reasons", [])

    def save(self, commit=True):
        instance = super().save(commit=False)
        patient = self.cleaned_data.get("patient_instance") or getattr(self.instance, "patient", None)
        if isinstance(patient, Patient):
            if not patient.pk and not patient.created_by_id and getattr(self, "actor", None) is not None:
                patient.created_by = self.actor
            if not patient.pk:
                patient.save()
            elif self.instance.pk or self.cleaned_data.get("patient_mode") != "existing":
                patient.save()
        instance.patient = patient
        if instance.patient_id:
            instance.sync_identity_from_patient()
        instance.ncd_flags = self.cleaned_data.get("ncd_flags", [])
        instance.anc_high_risk_reasons = self.cleaned_data.get("anc_high_risk_reasons", [])
        if commit:
            instance.save()
        return instance

    class Meta:
        model = Case
        fields = [
            "patient_mode",
            "selected_patient",
            "use_temporary_uhid",
            "uhid",
            "prefix",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "place",
            "age",
            "phone_number",
            "alternate_phone_number",
            "category",
            "subcategory",
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
            "ftnd",
            "lscs",
            "notes",
        ]
        widgets = {
            "lmp": forms.DateInput(attrs=dict(CRAYONS_DATEPICKER_ATTRS)),
            "edd": forms.DateInput(attrs=dict(CRAYONS_DATEPICKER_ATTRS)),
            "usg_edd": forms.DateInput(attrs=dict(CRAYONS_DATEPICKER_ATTRS)),
            "surgery_date": forms.DateInput(attrs=dict(CRAYONS_DATEPICKER_ATTRS)),
            "review_date": forms.DateInput(attrs=dict(CRAYONS_DATEPICKER_ATTRS)),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "date_of_birth": forms.DateInput(attrs=dict(CRAYONS_DATEPICKER_ATTRS)),
        }


class QuickEntryCaseForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        ensure_default_departments()
        super().__init__(*args, **kwargs)
        self.fields["prefix"].required = True
        self.fields["prefix"].label = "Prefix"
        self.fields["prefix"].choices = CASE_PREFIX_SELECT_CHOICES
        self.fields["category"].queryset = self.fields["category"].queryset.order_by("name")
        self.fields["age"].required = True
        self.fields["gender"].required = True
        self.fields["diagnosis"].required = True
        self.fields["review_date"].required = True
        self.fields["review_date"].input_formats = DATE_INPUT_FORMATS
        self._configure_subcategory_field()
        self.subcategory_option_groups = self._build_subcategory_option_groups()

    def _selected_category_for_subcategory(self):
        return _selected_category_from_form(self)

    def _configure_subcategory_field(self):
        _configure_case_subcategory_field(
            self.fields["subcategory"],
            category=self._selected_category_for_subcategory(),
            required=False,
            optional_copy=True,
        )

    def _build_subcategory_option_groups(self):
        groups = {}
        for category in self.fields["category"].queryset.only("id", "name"):
            group_name = case_subcategory_group_for_category_name(category.name)
            choices = list(case_subcategory_choices_for_category_name(category.name))
            if not choices:
                continue
            groups[str(category.pk)] = {
                "help_text": _case_subcategory_help_text(
                    subcategory_group=group_name,
                    optional_copy=True,
                    has_options=True,
                ),
                "options": [{"value": value, "label": label} for value, label in choices],
            }
        return groups

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        category_name = category.name.upper() if category else ""
        valid_subcategories = valid_case_subcategory_values_for_category_name(category_name)
        if cleaned_data.get("subcategory") not in valid_subcategories:
            cleaned_data["subcategory"] = ""
        return cleaned_data

    def _post_clean(self):
        self.instance._skip_workflow_validation = True
        super()._post_clean()

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance._skip_workflow_validation = True
        if not instance.created_by_id and getattr(self, "actor", None) is not None:
            instance.created_by = self.actor
        instance.status = CaseStatus.ACTIVE
        instance.metadata = {
            **(instance.metadata or {}),
            "entry_mode": "quick_entry",
            "details_pending": True,
        }
        patient = getattr(instance, "patient", None) or Patient()
        patient.uhid = (instance.uhid or generate_quick_entry_uhid()).strip().upper()
        patient.prefix = instance.prefix or ""
        patient.first_name = instance.first_name or ""
        patient.last_name = ""
        patient.gender = instance.gender or ""
        patient.age = instance.age
        patient.phone_number = ""
        patient.alternate_phone_number = ""
        if not patient.pk and not patient.created_by_id and getattr(self, "actor", None) is not None:
            patient.created_by = self.actor
        if commit:
            patient.save()
            instance.patient = patient
            instance.sync_identity_from_patient()
            instance.save()
        else:
            instance.patient = patient
            instance.sync_identity_from_patient()
        return instance

    class Meta:
        model = Case
        fields = ["prefix", "first_name", "age", "gender", "category", "subcategory", "review_date", "diagnosis"]
        widgets = {
            "review_date": forms.DateInput(attrs=dict(CRAYONS_DATEPICKER_ATTRS)),
        }


class PatientMergeForm(forms.Form):
    target_patient = forms.ModelChoiceField(
        queryset=Patient.objects.none(),
        required=True,
        label="Merge into patient",
    )

    def __init__(self, *args, source_patient=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_patient = source_patient
        queryset = Patient.objects.filter(merged_into__isnull=True).order_by("patient_name", "uhid")
        if source_patient and source_patient.pk:
            queryset = queryset.exclude(pk=source_patient.pk)
        self.fields["target_patient"].queryset = queryset


class TaskForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due_date"].input_formats = DATE_INPUT_FORMATS
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
            "due_date": forms.DateInput(attrs=dict(CRAYONS_DATEPICKER_ATTRS)),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class VitalEntryForm(StyledModelForm):
    hb_warning_message = "Hemoglobin is outside expected ANC range (4.0 to 13.0). The value was saved."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hb_warning = False
        self.fields["recorded_at"].label = "Recorded at"
        self.fields["bp_systolic"].label = "Systolic"
        self.fields["bp_diastolic"].label = "Diastolic"
        self.fields["pr"].label = "Pulse rate"
        self.fields["weight_kg"].label = "Weight"
        self.fields["weight_kg"].help_text = "Optional. Half-kilogram steps."
        self.fields["recorded_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["recorded_at"].widget.attrs.update({"step": 60})
        self.fields["bp_systolic"].widget = forms.NumberInput(
            attrs={"class": "form-control", "min": 70, "max": 240, "placeholder": "120"}
        )
        self.fields["bp_diastolic"].widget = forms.NumberInput(
            attrs={"class": "form-control", "min": 40, "max": 140, "placeholder": "80"}
        )
        self.fields["pr"].widget = forms.Select(attrs={"class": "form-select"}, choices=self._pr_choices())
        self.fields["spo2"].widget = forms.Select(attrs={"class": "form-select"}, choices=self._spo2_choices())
        self.fields["weight_kg"].widget = forms.Select(attrs={"class": "form-select"}, choices=self._weight_choices())
        self.fields["hemoglobin"].widget.attrs.update({"placeholder": "10.8", "inputmode": "decimal"})
        if not self.is_bound:
            if self.instance and self.instance.pk and self.instance.recorded_at:
                local_recorded_at = timezone.localtime(self.instance.recorded_at)
            else:
                local_recorded_at = timezone.localtime(timezone.now())
            self.initial["recorded_at"] = local_recorded_at.strftime("%Y-%m-%dT%H:%M")
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
        self.fields["task"].empty_label = "Select task"
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
            "can_patient_merge",
            "can_manage_settings",
        ]
        widgets = {
            "can_case_create": forms.CheckboxInput(),
            "can_case_edit": forms.CheckboxInput(),
            "can_task_create": forms.CheckboxInput(),
            "can_task_edit": forms.CheckboxInput(),
            "can_note_add": forms.CheckboxInput(),
            "can_patient_merge": forms.CheckboxInput(),
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
