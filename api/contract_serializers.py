"""OpenAPI-only serializers for the public mobile contract.

Runtime validation remains in forms/domain serializers; these serializers make every
APIView operation explicit and keep generated clients aligned with the JSON contract.
"""

from rest_framework import serializers


class ChoiceContractSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class SubcategoryContractSerializer(serializers.Serializer):
    value = serializers.CharField(allow_blank=True, allow_null=True)
    label = serializers.CharField(allow_blank=True, allow_null=True)
    icon_path = serializers.CharField(allow_blank=True, allow_null=True)


class CategoryContractSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()
    icon_path = serializers.CharField(allow_blank=True, allow_null=True)
    theme = serializers.DictField(child=serializers.CharField(), required=False)
    subcategories = SubcategoryContractSerializer(many=True, required=False)


class TaskCountsContractSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    open = serializers.IntegerField()
    today = serializers.IntegerField()
    upcoming = serializers.IntegerField()
    overdue = serializers.IntegerField()
    awaiting = serializers.IntegerField()
    completed = serializers.IntegerField()


class TaskContractSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    due_date = serializers.DateField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    task_type = serializers.CharField()
    task_type_label = serializers.CharField()
    frequency_label = serializers.CharField(allow_blank=True)
    assigned_user = serializers.CharField(allow_blank=True)
    assigned_user_id = serializers.IntegerField(allow_null=True)
    notes = serializers.CharField(allow_blank=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    can_complete = serializers.BooleanField()


class VitalContractSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    recorded_at = serializers.DateTimeField()
    server_received_at = serializers.DateTimeField()
    bp_systolic = serializers.IntegerField(allow_null=True)
    bp_diastolic = serializers.IntegerField(allow_null=True)
    blood_pressure_display = serializers.CharField(allow_blank=True)
    pr = serializers.IntegerField(allow_null=True)
    spo2 = serializers.IntegerField(allow_null=True)
    weight_kg = serializers.CharField(allow_null=True)
    hemoglobin = serializers.CharField(allow_null=True)
    summary = serializers.JSONField()


class CaseContractSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uhid = serializers.CharField()
    name = serializers.CharField()
    age = serializers.IntegerField(allow_null=True)
    sex = serializers.CharField(allow_blank=True, allow_null=True)
    sex_label = serializers.CharField(allow_blank=True)
    place = serializers.CharField(allow_blank=True)
    phone_number = serializers.CharField(allow_blank=True)
    category = CategoryContractSerializer()
    subcategory = SubcategoryContractSerializer()
    status = serializers.CharField()
    red_flag = serializers.BooleanField()
    red_flag_reasons = serializers.ListField(child=serializers.CharField())
    diagnosis = serializers.CharField(allow_blank=True)
    surgery_done = serializers.BooleanField()
    clinical_headline = serializers.ListField(child=serializers.CharField())
    task_counts = TaskCountsContractSerializer()
    next_task = TaskContractSerializer(allow_null=True)
    latest_vital = VitalContractSerializer(allow_null=True)
    updated_at = serializers.DateTimeField()


class CaseStatsContractSerializer(serializers.Serializer):
    today = serializers.IntegerField()
    upcoming = serializers.IntegerField()
    overdue = serializers.IntegerField()
    awaiting = serializers.IntegerField()
    red = serializers.IntegerField()


class CaseListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    stats = CaseStatsContractSerializer()
    results = CaseContractSerializer(many=True)


class CaseWriteRequestSerializer(serializers.Serializer):
    patient_mode = serializers.ChoiceField(choices=["new", "existing"], required=False)
    selected_patient = serializers.IntegerField(required=False, allow_null=True)
    use_temporary_uhid = serializers.BooleanField(required=False)
    uhid = serializers.CharField(required=False, allow_blank=True, max_length=64)
    prefix = serializers.CharField(required=False, allow_blank=True, max_length=3)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    gender = serializers.CharField(required=False, allow_blank=True)
    blood_group = serializers.CharField(required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    place = serializers.CharField(required=False, allow_blank=True, max_length=200)
    age = serializers.IntegerField(required=False, allow_null=True)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=10)
    alternate_phone_number = serializers.CharField(required=False, allow_blank=True, max_length=10)
    category = serializers.IntegerField(required=False)
    subcategory = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)
    diagnosis = serializers.CharField(required=False, allow_blank=True, max_length=255)
    ncd_flags = serializers.ListField(child=serializers.CharField(), required=False)
    referred_by = serializers.CharField(required=False, allow_blank=True, max_length=255)
    high_risk = serializers.BooleanField(required=False)
    anc_high_risk_reasons = serializers.ListField(child=serializers.CharField(), required=False)
    rch_number = serializers.CharField(required=False, allow_blank=True, max_length=32)
    rch_bypass = serializers.BooleanField(required=False)
    lmp = serializers.DateField(required=False, allow_null=True)
    edd = serializers.DateField(required=False, allow_null=True)
    usg_edd = serializers.DateField(required=False, allow_null=True)
    surgical_pathway = serializers.CharField(required=False, allow_blank=True)
    surgery_done = serializers.BooleanField(required=False)
    surgery_date = serializers.DateField(required=False, allow_null=True)
    review_frequency = serializers.CharField(required=False, allow_blank=True)
    review_date = serializers.DateField(required=False, allow_null=True)
    gravida = serializers.IntegerField(required=False, allow_null=True)
    para = serializers.IntegerField(required=False, allow_null=True)
    abortions = serializers.IntegerField(required=False, allow_null=True)
    living = serializers.IntegerField(required=False, allow_null=True)
    ftnd = serializers.IntegerField(required=False, allow_null=True)
    lscs = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    client_write_id = serializers.CharField(required=False, allow_blank=True, max_length=80)


class EditableCaseContractSerializer(CaseWriteRequestSerializer):
    id = serializers.IntegerField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This is an output snapshot, not a write envelope. Every editable value is
        # present so clients can safely patch one field without synthesizing defaults.
        self.fields.pop("client_write_id", None)
        for field in self.fields.values():
            field.required = True


class CaseWriteResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    case_id = serializers.IntegerField()
    case = CaseContractSerializer()
    editable_case = EditableCaseContractSerializer(required=False)


class CallLogContractSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    task_id = serializers.IntegerField(allow_null=True)
    mobile_outcome = serializers.CharField(required=False, allow_blank=True)
    outcome = serializers.CharField()
    outcome_label = serializers.CharField()
    notes = serializers.CharField(allow_blank=True)
    client_event_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField(help_text="Immutable server receipt time.")


class CaseDetailResponseSerializer(serializers.Serializer):
    case = CaseContractSerializer()
    web_case = serializers.JSONField(required=False)
    tasks = TaskContractSerializer(many=True)
    vitals = VitalContractSerializer(many=True)
    call_logs = CallLogContractSerializer(many=True)
    red_flag_reasons = serializers.ListField(child=serializers.CharField())


class CaseEditFormResponseSerializer(serializers.Serializer):
    can_edit = serializers.BooleanField()
    categories = CategoryContractSerializer(many=True)
    prefixes = ChoiceContractSerializer(many=True)
    blood_groups = ChoiceContractSerializer(many=True)
    genders = ChoiceContractSerializer(many=True)
    ncd_flags = ChoiceContractSerializer(many=True)
    anc_high_risk_reasons = ChoiceContractSerializer(many=True)
    surgical_pathways = ChoiceContractSerializer(many=True)
    review_frequencies = ChoiceContractSerializer(many=True)
    case = EditableCaseContractSerializer()


class TaskWriteRequestSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, max_length=200)
    due_date = serializers.DateField(required=False)
    status = serializers.CharField(required=False)
    assigned_user = serializers.IntegerField(required=False, allow_null=True)
    task_type = serializers.CharField(required=False)
    frequency_label = serializers.CharField(required=False, allow_blank=True, max_length=40)
    notes = serializers.CharField(required=False, allow_blank=True)
    client_write_id = serializers.CharField(required=False, allow_blank=True, max_length=80)


class TaskNoteRequestSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=1000)


class TaskWriteResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    task = TaskContractSerializer()
    case = CaseContractSerializer()


class CallWriteResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    call_log = CallLogContractSerializer()
    case = CaseContractSerializer()


class VitalsWriteResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    latest_vital_id = serializers.IntegerField()
    vital = VitalContractSerializer()
    case = CaseContractSerializer()


class VitalsThresholdsResponseSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    metrics = serializers.JSONField()
    status_labels = serializers.JSONField()


class MeResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    display_name = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
    capabilities = serializers.DictField(child=serializers.BooleanField())


class LogoutResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    deactivated_devices = serializers.IntegerField()


class DeviceTokenResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created = serializers.BooleanField()
    platform = serializers.CharField()
    app_version = serializers.CharField(allow_blank=True)
    device_label = serializers.CharField(allow_blank=True)


class NotificationContractSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    event_id = serializers.UUIDField(help_text="Opaque identifier carried by FCM.")
    type = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    case_id = serializers.IntegerField(allow_null=True)
    task_id = serializers.IntegerField(allow_null=True)
    payload = serializers.JSONField()
    read_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class NotificationsResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = NotificationContractSerializer(many=True)


class NotificationReadResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    read_at = serializers.DateTimeField()
    message = serializers.CharField()


class CategoriesResponseSerializer(serializers.Serializer):
    categories = CategoryContractSerializer(many=True)


class CaseFormMetadataResponseSerializer(CategoriesResponseSerializer):
    can_create = serializers.BooleanField()
    prefixes = ChoiceContractSerializer(many=True)
    blood_groups = ChoiceContractSerializer(many=True)
    genders = ChoiceContractSerializer(many=True)
    ncd_flags = ChoiceContractSerializer(many=True)
    anc_high_risk_reasons = ChoiceContractSerializer(many=True)
    surgical_pathways = ChoiceContractSerializer(many=True)
    review_frequencies = ChoiceContractSerializer(many=True)


class TaskFormMetadataResponseSerializer(serializers.Serializer):
    can_create = serializers.BooleanField()
    can_edit = serializers.BooleanField()
    can_reopen = serializers.BooleanField()
    default_status = serializers.CharField()
    task_types = ChoiceContractSerializer(many=True)
    statuses = ChoiceContractSerializer(many=True)
    assignable_users = serializers.ListField(child=serializers.DictField())


class PatientSearchResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uhid = serializers.CharField()
    name = serializers.CharField()


class PatientSearchResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PatientSearchResultSerializer(many=True)


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class ErrorResponseSerializer(serializers.Serializer):
    code = serializers.CharField(required=False)
    message = serializers.CharField()
    errors = serializers.JSONField(required=False)
