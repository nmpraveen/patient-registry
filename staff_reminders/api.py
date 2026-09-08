from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ReminderOccurrence
from .policy import assignees, authorized_staff, visible_reminders
from .serializers import (AssigneeSerializer, CompleteSerializer, CreateReminderSerializer,
                          OccurrenceSerializer, ReminderSerializer, UpdateReminderSerializer,
                          AssigneePageSerializer, OccurrencePageSerializer, ReminderPageSerializer)
from .services import StaleReminder, complete_occurrence, create_reminder, hospital_today, update_reminder


class IsAuthorizedStaff(BasePermission):
    def has_permission(self, request, view):
        return authorized_staff(request.user)


class ReminderPagination(PageNumberPagination):
    page_size = 50

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["server_now"] = timezone.now().isoformat()
        response.data["server_today"] = hospital_today().isoformat()
        return response


class StaffAPIView(APIView):
    permission_classes = [IsAuthorizedStaff]

    def handle_exception(self, exc):
        if isinstance(exc, StaleReminder):
            error = ValidationError(exc.messages)
            error.status_code = 409
            exc = error
        elif isinstance(exc, DjangoValidationError):
            exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return super().handle_exception(exc)

    def page(self, request, rows, serializer):
        pagination = ReminderPagination()
        result = pagination.paginate_queryset(rows, request, view=self)
        return pagination.get_paginated_response(serializer(result, many=True).data)


class ReminderList(StaffAPIView):
    @extend_schema(operation_id="staff_reminder_list", responses=ReminderPageSerializer, parameters=[OpenApiParameter("page", int), OpenApiParameter("is_active", str, enum=["true", "false"])])
    def get(self, request):
        rows = visible_reminders(request.user).select_related("assignee").order_by("-created_at", "-pk")
        if "is_active" in request.query_params:
            value = request.query_params["is_active"]
            if value not in ("true", "false"):
                raise ValidationError({"is_active": "Use true or false."})
            rows = rows.filter(is_active=value == "true")
        return self.page(request, rows, ReminderSerializer)

    @extend_schema(operation_id="staff_reminder_create", request=CreateReminderSerializer, responses={201: ReminderSerializer})
    def post(self, request):
        data = CreateReminderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reminder = create_reminder(request.user, data.validated_data, request=request)
        return Response(ReminderSerializer(reminder).data, status=201)


class ReminderDetail(StaffAPIView):
    @extend_schema(operation_id="staff_reminder_detail", responses=ReminderSerializer)
    def get(self, request, pk):
        reminder = get_object_or_404(visible_reminders(request.user).select_related("assignee"), pk=pk)
        return Response(ReminderSerializer(reminder).data)

    @extend_schema(operation_id="staff_reminder_update", request=UpdateReminderSerializer, responses=ReminderSerializer)
    def patch(self, request, pk):
        # Denied IDs are resolved before validating mutation details.
        get_object_or_404(visible_reminders(request.user), pk=pk)
        data = UpdateReminderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        version = values.pop("version")
        reminder = update_reminder(request.user, pk, values, version, request=request)
        return Response(ReminderSerializer(reminder).data)


def occurrence_rows(user, params):
    definitions = visible_reminders(user)
    if "reminder_id" in params:
        try:
            reminder_id = int(params["reminder_id"])
        except (ValueError, TypeError):
            raise ValidationError({"reminder_id": "Use an integer ID."})
        definition = get_object_or_404(definitions, pk=reminder_id)
        definitions = definitions.filter(pk=definition.pk)
    rows = ReminderOccurrence.objects.filter(reminder__in=definitions).select_related("reminder__assignee")
    status = params.get("status", "pending")
    if status in ("pending", "notices"):
        rows = rows.filter(completed_at__isnull=True, reminder__is_active=True)
        if status == "notices":
            rows = rows.filter(notice_date__lte=hospital_today())
    elif status == "completed":
        rows = rows.filter(completed_at__isnull=False)
    elif status != "all":
        raise ValidationError({"status": "Use pending, completed, all or notices."})
    return rows.order_by("due_date", "pk")


class OccurrenceList(StaffAPIView):
    @extend_schema(operation_id="staff_reminder_occurrence_list", responses=OccurrencePageSerializer, parameters=[OpenApiParameter("page", int), OpenApiParameter("reminder_id", int), OpenApiParameter("status", str, enum=["pending", "completed", "all", "notices"])])
    def get(self, request):
        return self.page(request, occurrence_rows(request.user, request.query_params), OccurrenceSerializer)


class OccurrenceComplete(StaffAPIView):
    @extend_schema(operation_id="staff_reminder_occurrence_complete", request=CompleteSerializer, responses=OccurrenceSerializer)
    def post(self, request, pk):
        data = CompleteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        occurrence = complete_occurrence(request.user, pk, data.validated_data["version"], request=request)
        return Response(OccurrenceSerializer(occurrence).data)


class AssigneeList(StaffAPIView):
    @extend_schema(operation_id="staff_reminder_assignee_list", responses=AssigneePageSerializer, parameters=[OpenApiParameter("page", int), OpenApiParameter("q", str)])
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) > 100:
            raise ValidationError({"q": "Use at most 100 characters."})
        rows = assignees()
        if query:
            rows = rows.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
        return self.page(request, rows, AssigneeSerializer)
