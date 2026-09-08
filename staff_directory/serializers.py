import re

from rest_framework import serializers

from .models import Contact


class PhoneSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    number = serializers.RegexField(r"^\+?[0-9 ()-]{3,32}$", max_length=32)
    extension = serializers.RegexField(r"^[0-9]{0,10}$", required=False, allow_blank=True, default="")

    def validate_number(self, value):
        if len(re.sub(r"\D", "", value)) < 3:
            raise serializers.ValidationError("Enter a phone number.")
        return value


class ContactSerializer(serializers.ModelSerializer):
    phones = PhoneSerializer(many=True, allow_empty=False)
    is_favourite = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = ("id", "name", "role_specialty", "organization", "phones", "notes",
                  "is_active", "is_favourite", "version", "updated_at")
        read_only_fields = ("id", "version", "updated_at")

    def get_is_favourite(self, obj) -> bool:
        annotated = getattr(obj, "favourite_for_user", None)
        if annotated is not None:
            return annotated
        return obj.favourites.filter(user=self.context["request"].user).exists()

    def validate_phones(self, value):
        if len(value) > 10:
            raise serializers.ValidationError("Use at most 10 phone numbers.")
        return value


class ContactUpdateSerializer(ContactSerializer):
    version = serializers.IntegerField(min_value=1, required=True)


class FavouriteSerializer(serializers.Serializer):
    is_favourite = serializers.BooleanField()
