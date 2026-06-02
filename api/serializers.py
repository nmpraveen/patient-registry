from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from patients.models import CallOutcome, VitalEntry


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    device_token = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DeviceTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=255)
    platform = serializers.CharField(max_length=32, required=False, default="android")
    app_version = serializers.CharField(max_length=64, required=False, allow_blank=True)
    device_label = serializers.CharField(max_length=120, required=False, allow_blank=True)


class ClientWriteSerializer(serializers.Serializer):
    client_write_id = serializers.CharField(max_length=80, required=False, allow_blank=True)


class TaskCompleteSerializer(ClientWriteSerializer):
    pass


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
    task_id = serializers.IntegerField(required=False, allow_null=True)
    attempted_at = serializers.DateTimeField(required=False, allow_null=True)


class VitalEntryCreateSerializer(ClientWriteSerializer):
    recorded_at = serializers.DateTimeField(required=False)
    bp_systolic = serializers.IntegerField(required=False, allow_null=True, min_value=70, max_value=240)
    bp_diastolic = serializers.IntegerField(required=False, allow_null=True, min_value=40, max_value=140)
    pr = serializers.IntegerField(required=False, allow_null=True, min_value=30, max_value=220)
    spo2 = serializers.IntegerField(required=False, allow_null=True, min_value=50, max_value=100)
    weight_kg = serializers.DecimalField(required=False, allow_null=True, max_digits=5, decimal_places=2, min_value=Decimal("30.0"), max_value=Decimal("120.0"))
    hemoglobin = serializers.DecimalField(required=False, allow_null=True, max_digits=4, decimal_places=1)

    metric_fields = ["bp_systolic", "bp_diastolic", "pr", "spo2", "weight_kg", "hemoglobin"]

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

    def update_vital(self, *, vital, user):
        data = dict(self.validated_data)
        data.pop("client_write_id", None)
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
