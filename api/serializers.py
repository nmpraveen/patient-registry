from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from patients.models import (
    CallOutcome,
    TaskStatus,
    VitalEntry,
    VITAL_BP_DIASTOLIC_MAX,
    VITAL_BP_DIASTOLIC_MIN,
    VITAL_BP_SYSTOLIC_MAX,
    VITAL_BP_SYSTOLIC_MIN,
    VITAL_PR_MAX,
    VITAL_PR_MIN,
    VITAL_SPO2_MAX,
    VITAL_SPO2_MIN,
    VITAL_WEIGHT_KG_MAX,
    VITAL_WEIGHT_KG_MIN,
)


MAX_CLIENT_FUTURE_SKEW = timedelta(minutes=5)
MAX_CLIENT_EVENT_LOOKBACK = timedelta(days=30)


def validate_client_event_timestamp(value):
    if value is None:
        return value
    now = timezone.now()
    if value > now + MAX_CLIENT_FUTURE_SKEW:
        raise serializers.ValidationError("Client event time cannot be more than 5 minutes in the future.")
    if value < now - MAX_CLIENT_EVENT_LOOKBACK:
        raise serializers.ValidationError("Client event time cannot be more than 30 days old.")
    return value


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    device_token = serializers.CharField(max_length=255, required=False, allow_blank=True)


class PatientSearchSerializer(serializers.Serializer):
    query = serializers.CharField(min_length=3, max_length=80, trim_whitespace=True)
    page_size = serializers.IntegerField(required=False, default=10, min_value=1, max_value=20)
    cursor = serializers.CharField(required=False, allow_null=True, allow_blank=False)


class CaseSearchSerializer(PatientSearchSerializer):
    page_size = serializers.IntegerField(required=False, default=20, min_value=1, max_value=20)
    bucket = serializers.ChoiceField(
        choices=["all", "today", "upcoming", "overdue", "awaiting", "red", "dormant", "edd_missing"],
        required=False,
        default="today",
    )
    assigned_to = serializers.ChoiceField(choices=["me", "all"], required=False, allow_blank=True)
    scope_context = serializers.ChoiceField(choices=["", "calls"], required=False, allow_blank=True, default="")
    category = serializers.ListField(child=serializers.CharField(max_length=80), required=False, default=list)
    subcategory = serializers.ListField(child=serializers.CharField(max_length=80), required=False, default=list)


class DeviceTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=255)
    platform = serializers.CharField(max_length=32, required=False, default="android")
    app_version = serializers.CharField(max_length=64, required=False, allow_blank=True)
    device_label = serializers.CharField(max_length=120, required=False, allow_blank=True)


class ClientWriteSerializer(serializers.Serializer):
    client_write_id = serializers.RegexField(
        regex=r"^[A-Za-z0-9._~-]+$",
        max_length=80,
        required=False,
        allow_blank=True,
        error_messages={"invalid": "Use an opaque ASCII write identifier."},
    )


class PatchControlSerializer(ClientWriteSerializer):
    base_updated_at = serializers.DateTimeField()
    base_values = serializers.DictField()


class TaskCompleteSerializer(ClientWriteSerializer):
    base_values = serializers.DictField(required=False)

    def validate_base_values(self, value):
        if set(value) != {"status", "due_date"}:
            raise serializers.ValidationError("Supply the observed status and due_date only.")
        serializers.ChoiceField(choices=TaskStatus.choices).run_validation(value["status"])
        parsed = serializers.DateField().run_validation(value["due_date"])
        return {"status": value["status"], "due_date": parsed.isoformat()}


class CallOutcomeSerializer(ClientWriteSerializer):
    outcome = serializers.ChoiceField(
        choices=[
            "reached",
            "no-answer",
            "no_answer",
            "busy",
            "wrong-number",
            "wrong_number",
            "attempted",
        ]
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    task_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    attempted_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_attempted_at(self, value):
        return validate_client_event_timestamp(value)

    def validate(self, attrs):
        if not attrs.get("task_id") and "reason" in attrs and not attrs["reason"]:
            raise serializers.ValidationError({"reason": "Enter a reason for a general patient call."})
        return attrs


class VitalEntryCreateSerializer(ClientWriteSerializer):
    recorded_at = serializers.DateTimeField(required=False)
    bp_systolic = serializers.IntegerField(required=False, allow_null=True, min_value=VITAL_BP_SYSTOLIC_MIN, max_value=VITAL_BP_SYSTOLIC_MAX)
    bp_diastolic = serializers.IntegerField(required=False, allow_null=True, min_value=VITAL_BP_DIASTOLIC_MIN, max_value=VITAL_BP_DIASTOLIC_MAX)
    pr = serializers.IntegerField(required=False, allow_null=True, min_value=VITAL_PR_MIN, max_value=VITAL_PR_MAX)
    spo2 = serializers.IntegerField(required=False, allow_null=True, min_value=VITAL_SPO2_MIN, max_value=VITAL_SPO2_MAX)
    weight_kg = serializers.DecimalField(required=False, allow_null=True, max_digits=5, decimal_places=2, min_value=VITAL_WEIGHT_KG_MIN, max_value=VITAL_WEIGHT_KG_MAX)
    hemoglobin = serializers.DecimalField(required=False, allow_null=True, max_digits=4, decimal_places=1)

    metric_fields = ["bp_systolic", "bp_diastolic", "pr", "spo2", "weight_kg", "hemoglobin"]

    def validate_recorded_at(self, value):
        return validate_client_event_timestamp(value)

    def validate(self, attrs):
        if not any(attrs.get(field) is not None for field in self.metric_fields):
            raise serializers.ValidationError("Enter at least one vitals metric.")
        if (attrs.get("bp_systolic") is None) ^ (attrs.get("bp_diastolic") is None):
            raise serializers.ValidationError("Enter both systolic and diastolic BP.")
        hemoglobin = attrs.get("hemoglobin")
        if hemoglobin is not None and (hemoglobin < Decimal("4.0") or hemoglobin > Decimal("13.0")):
            attrs["hemoglobin_warning"] = "Hemoglobin is outside expected ANC range (4.0 to 13.0). The value was saved."
        return attrs

    def create_vital(self, *, case, user):
        data = dict(self.validated_data)
        data.pop("client_write_id", None)
        warning = data.pop("hemoglobin_warning", "")
        recorded_at = data.pop("recorded_at", None) or timezone.now()
        vital = VitalEntry.objects.create(
            case=case,
            recorded_at=recorded_at,
            created_by=user,
            updated_by=user,
            **data,
        )
        return vital, warning


class VitalEntryUpdateSerializer(VitalEntryCreateSerializer):
    """Same validation as create, but applies the values to an existing entry."""

    base_updated_at = serializers.DateTimeField()
    base_values = serializers.DictField()

    def update_vital(self, *, vital, user):
        data = dict(self.validated_data)
        data.pop("client_write_id", None)
        data.pop("base_updated_at", None)
        data.pop("base_values", None)
        warning = data.pop("hemoglobin_warning", "")
        recorded_at = data.pop("recorded_at", None)
        # Partial update: only touch metrics the caller actually sent, so editing
        # one value (e.g. BP) never wipes the others that were left out of the payload.
        for field in self.metric_fields:
            if field in self.validated_data:
                setattr(vital, field, data.get(field))
        if recorded_at is not None:
            vital.recorded_at = recorded_at
        vital.updated_by = user
        if vital.created_by_id is None:
            vital.created_by = user
        vital.save()
        return vital, warning


def call_outcome_to_model_value(outcome):
    outcome = outcome.replace("-", "_")
    return {
        "reached": CallOutcome.ANSWERED_UNCERTAIN,
        "no_answer": CallOutcome.NO_ANSWER,
        "busy": CallOutcome.CALL_REJECTED,
        "wrong_number": CallOutcome.INVALID_NUMBER,
        "attempted": CallOutcome.NO_ANSWER,
    }[outcome]
