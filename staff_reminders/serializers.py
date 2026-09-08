from collections.abc import Mapping
from datetime import timezone
from rest_framework import serializers

from .models import Reminder, ReminderOccurrence


def display_name(user):
    return user.get_full_name() or user.get_username()


class ReminderSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField()
    assignee_id = serializers.IntegerField()
    created_at = serializers.DateTimeField(default_timezone=timezone.utc)
    updated_at = serializers.DateTimeField(default_timezone=timezone.utc)
    assignee_name = serializers.SerializerMethodField()
    assignee_active = serializers.BooleanField(source="assignee.is_active")
    can_edit = serializers.SerializerMethodField()
    can_assign = serializers.SerializerMethodField()

    class Meta:
        model = Reminder
        fields = ["id", "title", "owner_id", "assignee_id", "assignee_name", "assignee_active", "due_date",
                  "advance_notice_days", "recurrence", "is_active", "version", "created_at", "updated_at", "can_edit", "can_assign"]

    def get_assignee_name(self, obj) -> str:
        return display_name(obj.assignee)

    def get_can_edit(self, obj) -> bool:
        return True  # Serializer is used only after current scope is enforced.

    def get_can_assign(self, obj) -> bool:
        return True


class OccurrenceSerializer(serializers.ModelSerializer):
    reminder_id = serializers.IntegerField()
    completed_by_id = serializers.IntegerField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True, default_timezone=timezone.utc)
    definition_version = serializers.IntegerField(source="reminder.version")
    title = serializers.CharField(source="reminder.title")
    assignee_id = serializers.IntegerField(source="reminder.assignee_id")
    assignee_name = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(source="reminder.is_active")
    can_complete = serializers.SerializerMethodField()

    class Meta:
        model = ReminderOccurrence
        fields = ["id", "reminder_id", "title", "assignee_id", "assignee_name", "due_date", "notice_date",
                  "completed_at", "completed_by_id", "is_active", "can_complete", "definition_version"]

    def get_assignee_name(self, obj) -> str:
        return display_name(obj.reminder.assignee)

    def get_can_complete(self, obj) -> bool:
        return obj.reminder.is_active and obj.completed_at is None


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"non_field_errors": ["Expected an object."]})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({field: "Unknown or immutable field." for field in sorted(unknown)})
        return super().to_internal_value(data)


class CreateReminderSerializer(StrictSerializer):
    title = serializers.CharField(max_length=200)
    assignee_id = serializers.IntegerField(min_value=1)
    due_date = serializers.DateField()
    advance_notice_days = serializers.IntegerField(min_value=0, max_value=365, default=0)
    recurrence = serializers.ChoiceField(choices=Reminder.Recurrence.choices, default=Reminder.Recurrence.ONCE)


class UpdateReminderSerializer(StrictSerializer):
    version = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=200, required=False)
    assignee_id = serializers.IntegerField(min_value=1, required=False)
    advance_notice_days = serializers.IntegerField(min_value=0, max_value=365, required=False)
    is_active = serializers.BooleanField(required=False)


class CompleteSerializer(StrictSerializer):
    version = serializers.IntegerField(min_value=1)


class AssigneeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.SerializerMethodField()

    def get_name(self, obj) -> str:
        return display_name(obj)


class PageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    server_now = serializers.DateTimeField()
    server_today = serializers.DateField()


class ReminderPageSerializer(PageSerializer):
    results = ReminderSerializer(many=True)


class OccurrencePageSerializer(PageSerializer):
    results = OccurrenceSerializer(many=True)


class AssigneePageSerializer(PageSerializer):
    results = AssigneeSerializer(many=True)
