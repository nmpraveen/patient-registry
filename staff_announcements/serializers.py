from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from patients.models import RoleSetting
from .models import Announcement


class PublisherSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class AnnouncementSerializer(serializers.ModelSerializer):
    audience_role_ids = serializers.PrimaryKeyRelatedField(
        source="audience_roles", many=True, queryset=RoleSetting.objects.all(), required=False)
    publisher = serializers.SerializerMethodField()
    server_now = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ("id", "text", "priority", "audience", "audience_role_ids", "starts_at", "ends_at",
                  "publisher", "is_active", "version", "updated_at", "server_now")
        read_only_fields = ("id", "version", "updated_at")

    @classmethod
    def _value(cls, attrs, instance, key):
        return attrs.get(key, getattr(instance, key, None))

    def validate(self, attrs):
        instance = self.instance
        start = self._value(attrs, instance, "starts_at")
        end = self._value(attrs, instance, "ends_at")
        if start and end and end <= start:
            raise serializers.ValidationError({"ends_at": "Expiry must follow the start."})
        audience = self._value(attrs, instance, "audience")
        roles = attrs.get("audience_roles")
        if roles is None:
            roles = list(instance.audience_roles.all()) if instance else []
        if audience == Announcement.Audience.SELECTED_ROLES and not roles:
            raise serializers.ValidationError({"audience_role_ids": "Select at least one role."})
        if audience == Announcement.Audience.ALL_STAFF:
            attrs["audience_roles"] = []
        return attrs

    def get_server_now(self, obj) -> str:
        return timezone.now().isoformat()

    @extend_schema_field(PublisherSerializer(allow_null=True))
    def get_publisher(self, obj):
        if obj.publisher is None:
            return None
        return {"id": obj.publisher_id, "name": obj.publisher.get_full_name() or obj.publisher.get_username()}


class AnnouncementUpdateSerializer(AnnouncementSerializer):
    version = serializers.IntegerField(min_value=1, required=True)
