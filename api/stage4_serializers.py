from rest_framework import serializers


class TimelineEventSerializer(serializers.Serializer):
    id = serializers.CharField()
    event_type = serializers.CharField()
    event_label = serializers.CharField()
    timestamp = serializers.DateTimeField()
    actor = serializers.CharField()
    task_title = serializers.CharField(allow_blank=True)
    headline = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    details = serializers.CharField(allow_blank=True)


class TimelinePageSerializer(serializers.Serializer):
    results = TimelineEventSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    timezone = serializers.CharField()


class UpcomingTaskSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    case_id = serializers.IntegerField()
    patient_name = serializers.CharField()
    department = serializers.CharField()
    title = serializers.CharField()
    due_date = serializers.DateField()
    assigned_user_id = serializers.IntegerField(allow_null=True)
    assigned_user_name = serializers.CharField(allow_blank=True)


class UpcomingPageSerializer(serializers.Serializer):
    hospital_today = serializers.DateField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    timezone = serializers.CharField()
    results = UpcomingTaskSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)


class UpcomingQuerySerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False)
    cursor = serializers.CharField(required=False, allow_null=True)
    assigned_to = serializers.ChoiceField(choices=["me", "all"], required=False)
    scope_context = serializers.ChoiceField(choices=["", "calls"], required=False, default="")
    category = serializers.ListField(child=serializers.CharField(max_length=80), required=False, default=list)
    subcategory = serializers.ListField(child=serializers.CharField(max_length=80), required=False, default=list)


class UpcomingSearchSerializer(UpcomingQuerySerializer):
    query = serializers.CharField(min_length=3, max_length=80, trim_whitespace=True)


class RelatedCaseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    department = serializers.CharField()
    diagnosis = serializers.CharField(allow_blank=True)
    status = serializers.CharField()


class RelatedCasesPageSerializer(serializers.Serializer):
    results = RelatedCaseSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
