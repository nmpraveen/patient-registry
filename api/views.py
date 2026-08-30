import hashlib
import json
import re
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Max, Min, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.crypto import salted_hmac
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from patients.models import (
    ActivityEventType,
    AuditEvent,
    AncHighRiskReason,
    BloodGroup,
    CallLog,
    Case,
    CasePrefix,
    CaseStatus,
    DepartmentConfig,
    Gender,
    NonCommunicableDisease,
    ReviewFrequency,
    RoleSetting,
    SurgicalPathway,
    Task,
    TaskStatus,
    TaskType,
    VitalEntry,
    UserSecurityState,
    build_default_tasks,
    cancel_open_rch_reminders,
    case_subcategory_choices_for_category_name,
    ensure_rch_reminder_task,
    frequency_to_days,
    is_anc_case,
)
from patients.audit import record_audit_event
from patients.auth_security import current_auth_version
from patients.theme import build_theme_category_colors, resolve_category_theme
from patients.vitals_thresholds import vitals_thresholds_payload
from patients.forms import CaseForm, TaskForm
from patients.intake_access import resolve_case_intake_patient
from patients.policy import effective_role_policy
from patients.views import (
    CASE_CATEGORY_GROUP_FILTERS,
    _blood_pressure_display,
    _build_case_detail_json_payload,
    _build_latest_vitals_summary,
    _build_upcoming_call_filters,
    _can_access_upcoming_calls,
    _can_reopen_tasks,
    _accessible_case_queryset,
    _accessible_task_queryset,
    _accessible_vital_queryset,
    _complete_task_inline,
    _dashboard_category_icon_path,
    _dashboard_subcategory_icon_path,
    _display_user_name,
    _patient_search_queryset,
    _reopen_task_follow_up_cleanup,
    _save_task_note_inline,
    _visible_case_queryset,
    can_access_case_data,
    create_case_activity,
    has_all_case_scope,
    has_capability,
    can_transition_grey_tasks,
    role_data_scope_payload,
)

from . import contract_serializers as contract
from .cursors import CursorValidationError, decode_cursor, encode_cursor
from .models import MobileDatasetState, MobileDeviceToken, MobileNotification, MobileWriteReceipt
from .notifications import (
    GENERIC_NOTIFICATION_COPY,
    authorized_notification_queryset,
    purge_expired_mobile_notifications,
    purge_expired_mobile_receipts,
    purge_stale_notifications_for_user,
    notification_epoch_for_user,
)
from .permissions import HasMobileCaseAccess
from .serializers import (
    CallOutcomeSerializer,
    CaseSearchSerializer,
    ClientWriteSerializer,
    DeviceTokenSerializer,
    LogoutSerializer,
    PatientSearchSerializer,
    PatchControlSerializer,
    TaskCompleteSerializer,
    VitalEntryCreateSerializer,
    VitalEntryUpdateSerializer,
    call_outcome_to_model_value,
)
from .throttles import DatabaseSearchThrottle
from .authentication import token_user, validate_token_auth_version


class MobilePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _user_role_labels(user):
    if user.is_superuser:
        return ["Superuser"]
    return list(user.groups.order_by("name").values_list("name", flat=True))


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="mobile_me_retrieve",
        responses={200: contract.MeResponseSerializer},
    )
    def get(self, request):
        return Response(
            {
                "id": request.user.id,
                "username": request.user.get_username(),
                "display_name": _display_user_name(request.user) or request.user.get_username(),
                "roles": _user_role_labels(request.user),
                "capabilities": {
                    "case_create": has_capability(request.user, "case_create"),
                    "case_edit": has_capability(request.user, "case_edit"),
                    "task_create": has_capability(request.user, "task_create"),
                    "task_edit": has_capability(request.user, "task_edit"),
                    "task_reopen": has_capability(request.user, "task_reopen"),
                    "note_add": has_capability(request.user, "note_add"),
                    "manage_settings": has_capability(request.user, "manage_settings"),
                },
                "data_scope": role_data_scope_payload(request.user),
            }
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="mobile_auth_logout",
        request=LogoutSerializer,
        responses={200: contract.LogoutResponseSerializer, 400: contract.LogoutResponseSerializer},
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device_token = serializer.validated_data.get("device_token", "").strip()
        try:
            refresh = RefreshToken(serializer.validated_data["refresh"])
            refresh_user = token_user(refresh)
            validate_token_auth_version(refresh, refresh_user)
            access_device_id = (request.auth or {}).get("mobile_device_id")
            refresh_device_id = refresh.get("mobile_device_id")
            if refresh_user.pk != request.user.pk or access_device_id != refresh_device_id:
                raise TokenError("Token binding mismatch.")
        except (InvalidToken, TokenError, TypeError, ValueError):
            record_audit_event(
                category=AuditEvent.Category.IAM,
                action="authentication.jwt.logout_failed",
                outcome=AuditEvent.Outcome.DENIED,
                actor=request.user,
                request=request,
                object_type="user",
                object_id=request.user.pk,
            )
            return Response(
                {
                    "message": "Logout token binding is invalid.",
                    "deactivated_devices": 0,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                devices = MobileDeviceToken.objects.select_for_update().filter(
                    user=request.user,
                    is_active=True,
                )
                if device_token:
                    devices = devices.filter(token=device_token)
                deactivated_count = devices.update(is_active=False)
                refresh.blacklist()
        except TokenError:
            return Response(
                {"message": "Logout token binding is invalid.", "deactivated_devices": 0},
                status=status.HTTP_400_BAD_REQUEST,
            )
        record_audit_event(
            category=AuditEvent.Category.IAM,
            action="authentication.jwt.logged_out",
            actor=request.user,
            request=request,
            object_type="user",
            object_id=request.user.pk,
            metadata={"deactivated_device_count": deactivated_count},
        )
        return Response(
            {"message": "Logged out.", "deactivated_devices": deactivated_count},
            status=status.HTTP_200_OK,
        )


def _red_flag_query():
    return Q(high_risk=True) | ~Q(anc_high_risk_reasons=[]) | ~Q(ncd_flags=[])


def _default_assigned_to_scope(user):
    return "all" if has_all_case_scope(user) else "me"


def _assigned_to_scope(request):
    raw_value = request.GET.get("assigned_to")
    assigned_to = (raw_value if raw_value is not None else _default_assigned_to_scope(request.user)).strip()
    return assigned_to or _default_assigned_to_scope(request.user)


def _can_use_all_assigned_scope(request):
    if has_all_case_scope(request.user):
        return True
    scope_context = request.GET.get("scope_context", "").strip()
    return scope_context == "calls" and _can_access_upcoming_calls(request.user)


def _calls_scope_query(request):
    scope_context = request.GET.get("scope_context", "").strip()
    if scope_context != "calls" or not _can_access_upcoming_calls(request.user):
        return Q()
    filters = _build_upcoming_call_filters(request.GET.get("range"))
    return Q(tasks__status=TaskStatus.SCHEDULED, tasks__due_date__range=(filters["range_start"], filters["range_end"]))


def _apply_scope_filters(queryset, request, *, include_bucket=True):
    today = timezone.localdate()
    assigned_to = _assigned_to_scope(request)
    if assigned_to == "all" and not _can_use_all_assigned_scope(request):
        assigned_to = "me"
    if assigned_to == "me":
        queryset = queryset.filter(tasks__assigned_user=request.user)
    elif assigned_to != "all":
        queryset = queryset.none()

    calls_scope_query = _calls_scope_query(request)
    if calls_scope_query:
        queryset = queryset.filter(calls_scope_query)

    raw_category_values = [value for value in request.GET.getlist("category") if value]
    category_query = Q()
    for raw_category in raw_category_values:
        if raw_category.isdigit():
            category_query |= Q(category_id=int(raw_category))
        elif raw_category in CASE_CATEGORY_GROUP_FILTERS:
            category_query |= CASE_CATEGORY_GROUP_FILTERS[raw_category]
        else:
            category_query |= Q(category__name__iexact=raw_category)
    if raw_category_values:
        queryset = queryset.filter(category_query)

    raw_subcategories = [value for value in request.GET.getlist("subcategory") if value]
    if raw_subcategories:
        queryset = queryset.filter(subcategory__in=raw_subcategories)

    if include_bucket:
        bucket = request.GET.get("bucket", "today").strip() or "today"
        if bucket in {"all", "*"}:
            pass
        elif bucket == "today":
            queryset = queryset.filter(tasks__status=TaskStatus.SCHEDULED, tasks__due_date=today)
        elif bucket == "upcoming":
            queryset = queryset.filter(tasks__status=TaskStatus.SCHEDULED, tasks__due_date__gt=today)
        elif bucket == "overdue":
            queryset = queryset.filter(tasks__due_date__lt=today).exclude(
                tasks__status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED]
            )
        elif bucket == "awaiting":
            queryset = queryset.filter(tasks__status=TaskStatus.AWAITING_REPORTS)
        elif bucket == "red":
            queryset = queryset.filter(_red_flag_query())
    return queryset.distinct()


def _apply_case_search_body_filters(queryset, user, values, *, include_bucket=True):
    today = timezone.localdate()
    assigned_to = values.get("assigned_to") or _default_assigned_to_scope(user)
    scope_context = values.get("scope_context", "")
    can_use_all = has_all_case_scope(user) or (
        scope_context == "calls" and _can_access_upcoming_calls(user)
    )
    if assigned_to == "all" and not can_use_all:
        assigned_to = "me"
    if assigned_to == "me":
        queryset = queryset.filter(tasks__assigned_user=user)
    elif assigned_to != "all":
        queryset = queryset.none()

    if scope_context == "calls" and _can_access_upcoming_calls(user):
        filters = _build_upcoming_call_filters(None)
        queryset = queryset.filter(
            tasks__status=TaskStatus.SCHEDULED,
            tasks__due_date__range=(filters["range_start"], filters["range_end"]),
        )

    category_values = values.get("category") or []
    category_query = Q()
    for raw_category in category_values:
        if str(raw_category).isdigit():
            category_query |= Q(category_id=int(raw_category))
        elif raw_category in CASE_CATEGORY_GROUP_FILTERS:
            category_query |= CASE_CATEGORY_GROUP_FILTERS[raw_category]
        else:
            category_query |= Q(category__name__iexact=raw_category)
    if category_values:
        queryset = queryset.filter(category_query)

    subcategories = values.get("subcategory") or []
    if subcategories:
        queryset = queryset.filter(subcategory__in=subcategories)

    if include_bucket:
        bucket = values.get("bucket") or "today"
        if bucket == "today":
            queryset = queryset.filter(tasks__status=TaskStatus.SCHEDULED, tasks__due_date=today)
        elif bucket == "upcoming":
            queryset = queryset.filter(tasks__status=TaskStatus.SCHEDULED, tasks__due_date__gt=today)
        elif bucket == "overdue":
            queryset = queryset.filter(tasks__due_date__lt=today).exclude(
                tasks__status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED]
            )
        elif bucket == "awaiting":
            queryset = queryset.filter(tasks__status=TaskStatus.AWAITING_REPORTS)
        elif bucket == "red":
            queryset = queryset.filter(_red_flag_query())
    return queryset.distinct()


def _counter_payload(base_queryset):
    today = timezone.localdate()
    return {
        "today": base_queryset.filter(tasks__status=TaskStatus.SCHEDULED, tasks__due_date=today).distinct().count(),
        "upcoming": base_queryset.filter(tasks__status=TaskStatus.SCHEDULED, tasks__due_date__gt=today).distinct().count(),
        "overdue": base_queryset.filter(tasks__due_date__lt=today)
        .exclude(tasks__status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED])
        .distinct()
        .count(),
        "awaiting": base_queryset.filter(tasks__status=TaskStatus.AWAITING_REPORTS).distinct().count(),
        "red": base_queryset.filter(_red_flag_query()).distinct().count(),
    }


def _task_counts(tasks, today):
    return {
        "total": len(tasks),
        "open": sum(1 for task in tasks if task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}),
        "today": sum(1 for task in tasks if task.status == TaskStatus.SCHEDULED and task.due_date == today),
        "upcoming": sum(1 for task in tasks if task.status == TaskStatus.SCHEDULED and task.due_date > today),
        "overdue": sum(
            1
            for task in tasks
            if task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED} and task.due_date < today
        ),
        "awaiting": sum(1 for task in tasks if task.status == TaskStatus.AWAITING_REPORTS),
        "completed": sum(1 for task in tasks if task.status == TaskStatus.COMPLETED),
    }


def _risk_reasons(case):
    reasons = []
    if case.high_risk:
        reasons.append("High risk")
    reasons.extend(case.anc_high_risk_reason_labels)
    reasons.extend(case.ncd_flag_labels)
    return list(dict.fromkeys(reasons))


def _serialize_task(task, *, can_complete):
    return {
        "id": task.id,
        "title": task.title,
        "due_date": task.due_date.isoformat(),
        "status": task.status,
        "status_label": task.get_status_display(),
        "task_type": task.task_type,
        "task_type_label": task.get_task_type_display(),
        "frequency_label": task.frequency_label,
        "assigned_user": _display_user_name(task.assigned_user) if task.assigned_user_id else "",
        "assigned_user_id": task.assigned_user_id,
        "notes": task.notes or "",
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "updated_at": task.updated_at.isoformat(),
        "can_complete": can_complete and task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED},
    }


def _serialize_vital(vital):
    return {
        "id": vital.id,
        "recorded_at": _iso_datetime(vital.recorded_at),
        "server_received_at": _iso_datetime(vital.created_at),
        "updated_at": _iso_datetime(vital.updated_at),
        "bp_systolic": vital.bp_systolic,
        "bp_diastolic": vital.bp_diastolic,
        "blood_pressure_display": _blood_pressure_display(vital.bp_systolic, vital.bp_diastolic),
        "pr": vital.pr,
        "spo2": vital.spo2,
        "weight_kg": str(vital.weight_kg) if vital.weight_kg is not None else None,
        "hemoglobin": str(vital.hemoglobin) if vital.hemoglobin is not None else None,
        "summary": _build_latest_vitals_summary(vital),
    }


def _serialize_case_row(case, *, user, today, theme_category_colors):
    tasks = list(getattr(case, "prefetched_mobile_tasks", []))
    latest_vital = next(iter(getattr(case, "prefetched_mobile_vitals", [])), None)
    open_tasks = [task for task in tasks if task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}]
    next_task = open_tasks[0] if open_tasks else None
    category_theme = resolve_category_theme(theme_category_colors, case.category)
    can_complete = has_capability(user, "task_edit")
    return {
        "id": case.id,
        "uhid": case.uhid,
        "name": case.full_name or case.patient_name,
        "age": case.age,
        "sex": case.gender,
        "sex_label": case.get_gender_display() if case.gender else "",
        "place": case.place,
        "phone_number": case.phone_number,
        "category": {
            "id": case.category_id,
            "name": case.category.name,
            "icon_path": _dashboard_category_icon_path(case.category.name),
            "theme": category_theme,
        },
        "subcategory": {
            "value": case.subcategory,
            "label": case.get_subcategory_display() if case.subcategory else "",
            "icon_path": _dashboard_subcategory_icon_path(case.subcategory),
        },
        "status": case.status,
        "red_flag": case.has_risk_factors,
        "red_flag_reasons": _risk_reasons(case),
        "diagnosis": case.diagnosis,
        "surgery_done": case.surgery_done,
        "clinical_headline": case.clinical_headline_items,
        "task_counts": _task_counts(tasks, today),
        "next_task": _serialize_task(next_task, can_complete=can_complete) if next_task else None,
        "latest_vital": _serialize_vital(latest_vital) if latest_vital else None,
        "updated_at": case.updated_at.isoformat(),
    }


def _mobile_case_payload(case, *, user):
    today = timezone.localdate()
    tasks = list(case.tasks.select_related("assigned_user").order_by("due_date", "id"))
    latest_vital = case.vitals.order_by("-recorded_at", "-id").first()
    case.prefetched_mobile_tasks = tasks
    case.prefetched_mobile_vitals = [latest_vital] if latest_vital else []
    theme_category_colors = build_theme_category_colors([case.category] if getattr(case, "category", None) else [])
    return _serialize_case_row(case, user=user, today=today, theme_category_colors=theme_category_colors)


class CaseListView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_cases_list",
        parameters=[
            OpenApiParameter("bucket", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("assigned_to", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("scope_context", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY, many=True, required=False),
            OpenApiParameter("subcategory", OpenApiTypes.STR, OpenApiParameter.QUERY, many=True, required=False),
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("page_size", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: contract.CaseListResponseSerializer},
    )
    def get(self, request):
        if "q" in request.query_params:
            record_audit_event(
                category=AuditEvent.Category.DATA,
                action="case.search_attempt",
                outcome=AuditEvent.Outcome.DENIED,
                actor=request.user,
                request=request,
                object_type="case_directory",
                metadata={
                    "search_class": "url_parameters_rejected",
                    "normalized_length": 0,
                    "result_count": 0,
                    "scope": role_data_scope_payload(request.user),
                },
            )
            return Response(
                {"code": "search_parameters_in_url", "message": "Case search must use the POST search endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        today = timezone.localdate()
        base_queryset = _apply_scope_filters(
            _visible_case_queryset(
                Case.objects.select_related("category").filter(status=CaseStatus.ACTIVE)
            ),
            request,
            include_bucket=False,
        )
        filtered_queryset = _apply_scope_filters(base_queryset, request, include_bucket=True).annotate(
            next_due=Min(
                "tasks__due_date",
                filter=~Q(tasks__status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
            ),
            latest_activity_at=Max("activity_logs__created_at"),
        )
        filtered_queryset = filtered_queryset.order_by("next_due", "-updated_at", "id")
        task_queryset = Task.objects.select_related("assigned_user").order_by("due_date", "id")
        filtered_queryset = filtered_queryset.prefetch_related(
            Prefetch("tasks", queryset=task_queryset, to_attr="prefetched_mobile_tasks"),
            Prefetch("vitals", queryset=VitalEntry.objects.order_by("-recorded_at", "-id"), to_attr="prefetched_mobile_vitals"),
        )

        paginator = MobilePagination()
        page = paginator.paginate_queryset(filtered_queryset, request, view=self)
        categories = [case.category for case in page if getattr(case, "category", None) is not None]
        theme_category_colors = build_theme_category_colors(categories)
        results = [
            _serialize_case_row(case, user=request.user, today=today, theme_category_colors=theme_category_colors)
            for case in page
        ]
        return Response(
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "stats": _counter_payload(base_queryset),
                "results": results,
            }
        )

    @extend_schema(
        operation_id="mobile_cases_create",
        request=contract.CaseCreateRequestSerializer,
        responses={
            201: contract.CaseWriteResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            409: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request):
        if not has_capability(request.user, "case_create"):
            return Response(
                {"message": "You do not have permission to create cases."},
                status=status.HTTP_403_FORBIDDEN,
            )
        write_serializer = ClientWriteSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        replay_response = _idempotent_replay_response(
            request,
            write_serializer,
            "case_create",
            target_type="collection",
        )
        if replay_response is not None:
            return replay_response

        if request.data.get("patient_mode") == "existing" and request.data.get("selected_patient"):
            if resolve_case_intake_patient(
                actor=request.user,
                patient_id=request.data.get("selected_patient"),
            ) is None:
                scope = role_data_scope_payload(request.user)
                record_audit_event(
                    category=AuditEvent.Category.CLINICAL,
                    action="case.intake_patient_selection_denied",
                    outcome=AuditEvent.Outcome.DENIED,
                    actor=request.user,
                    request=request,
                    metadata={
                        "case_data_scope": scope["case_data_scope"],
                        "intake_patient_lookup": scope["intake_patient_lookup"],
                    },
                )
                return Response(
                    {"message": "Existing patient selection is not permitted."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        form = CaseForm(data=request.data, actor=request.user)
        form.instance.created_by = request.user
        if not form.is_valid():
            return Response(
                {"message": "Please fix the highlighted fields.", "errors": _form_errors(form)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def apply_write():
            with transaction.atomic():
                if form.cleaned_data.get("patient_mode") == "existing":
                    try:
                        form.revalidate_intake_selection(lock=True)
                    except ValidationError as exc:
                        raise PermissionDenied(
                            "Existing patient selection is not permitted."
                        ) from exc
                case = form.save()
                if case.review_frequency and not case.review_date:
                    case.review_date = timezone.localdate() + timedelta(
                        days=frequency_to_days(case.review_frequency)
                    )
                    case.save(update_fields=["review_date", "updated_at", "patient_name"])
                created_tasks = build_default_tasks(case, request.user)
                create_case_activity(
                    case=case,
                    user=request.user,
                    event_type=ActivityEventType.SYSTEM,
                    note=f"Case created from mobile with {len(created_tasks)} starter task(s)",
                )
                ensure_rch_reminder_task(case, request.user)
            return {
                "message": "Case created.",
                "case_id": case.id,
                "case": _mobile_case_payload(case, user=request.user),
            }, status.HTTP_201_CREATED

        return _idempotent_response(
            request,
            write_serializer,
            "case_create",
            apply_write,
            target_type="collection",
        )


def _form_errors(form):
    return {
        field: [str(error) for error in errors]
        for field, errors in form.errors.items()
    }


class CaseDetailView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_case_retrieve",
        responses={200: contract.CaseDetailResponseSerializer, 404: contract.ErrorResponseSerializer},
    )
    def get(self, request, pk):
        case = get_object_or_404(
            _accessible_case_queryset(request.user, Case.objects.select_related("category")),
            pk=pk,
        )
        payload = _build_case_detail_json_payload(case, user=request.user)
        tasks = list(case.tasks.select_related("assigned_user").order_by("due_date", "id"))
        vitals = list(case.vitals.order_by("-recorded_at", "-id")[:25])
        payload["web_case"] = payload["case"]
        payload["case"] = _mobile_case_payload(case, user=request.user)
        payload["tasks"] = [_serialize_task(task, can_complete=has_capability(request.user, "task_edit")) for task in tasks]
        payload["vitals"] = [_serialize_vital(vital) for vital in vitals]
        payload["red_flag_reasons"] = _risk_reasons(case)
        payload["call_logs"] = [
            {
                "id": log.id,
                "task_id": log.task_id,
                "outcome": log.outcome,
                "outcome_label": log.get_outcome_display(),
                "notes": log.notes,
                "client_event_at": log.client_event_at.isoformat() if log.client_event_at else None,
                "created_at": log.created_at.isoformat(),
            }
            for log in case.call_logs.select_related("task").order_by("-created_at", "-id")[:20]
        ]
        return Response(payload)

    @extend_schema(
        operation_id="mobile_case_partial_update",
        request=contract.CasePatchRequestSerializer,
        responses={
            200: contract.CasePatchResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            404: contract.ErrorResponseSerializer,
            409: contract.ErrorResponseSerializer,
        },
    )
    def patch(self, request, pk):
        if not has_capability(request.user, "case_edit"):
            return Response(
                {"message": "You do not have permission to edit cases."},
                status=status.HTTP_403_FORBIDDEN,
            )
        get_object_or_404(_accessible_case_queryset(request.user), pk=pk)
        control = PatchControlSerializer(data=request.data)
        control.is_valid(raise_exception=True)
        replay = _idempotent_replay_response(
            request,
            control,
            "case_update",
            target_type="case",
            target_id=pk,
        )
        if replay is not None:
            return replay

        def apply_write():
            case = get_object_or_404(
                _accessible_case_queryset(
                    request.user,
                    Case.objects.select_for_update(of=("self",)).select_related("category", "patient"),
                ),
                pk=pk,
            )
            old_status = case.status
            current_values = _case_edit_payload(case)
            conflicts = _optimistic_patch_conflicts(
                current_values=current_values,
                request_data=request.data,
                base_values=control.validated_data["base_values"],
                base_updated_at=control.validated_data["base_updated_at"],
                updated_at=case.updated_at,
            )
            if conflicts:
                return _optimistic_conflict_response(conflicts)
            data = dict(current_values)
            data.update(
                {key: value for key, value in request.data.items() if key not in PATCH_CONTROL_FIELDS}
            )
            form = CaseForm(data=data, instance=case, actor=request.user)
            if not form.is_valid():
                return {
                    "code": "invalid_request",
                    "message": "Please fix the highlighted fields.",
                    "errors": _form_errors(form),
                }, status.HTTP_400_BAD_REQUEST
            new_status = form.cleaned_data.get("status") or old_status
            grey_list_cutoff = timezone.localdate() - timedelta(days=30)
            has_grey_tasks = case.tasks.exclude(status=TaskStatus.COMPLETED).filter(
                due_date__lt=grey_list_cutoff
            ).exists()
            if (
                has_grey_tasks
                and new_status in [CaseStatus.LOSS_TO_FOLLOW_UP, CaseStatus.ACTIVE]
                and not can_transition_grey_tasks(request.user, fresh=True)
            ):
                message = "Your role does not allow this Grey List status transition."
                return {
                    "code": "invalid_request",
                    "message": message,
                    "errors": {"status": [message]},
                }, status.HTTP_400_BAD_REQUEST
            if old_status != new_status:
                create_case_activity(
                    case=case,
                    user=request.user,
                    event_type=ActivityEventType.SYSTEM,
                    note=f"Case status changed: {old_status} -> {new_status}",
                )
            updated = form.save()
            if not is_anc_case(updated) or updated.rch_number:
                cancel_open_rch_reminders(updated)
            else:
                ensure_rch_reminder_task(updated, request.user)
            create_case_activity(
                case=updated,
                user=request.user,
                event_type=ActivityEventType.SYSTEM,
                note="Case updated from mobile.",
            )
            return {
                "message": "Case updated.",
                "case_id": updated.id,
                "case": _mobile_case_payload(updated, user=request.user),
                "editable_case": _case_edit_payload(updated),
            }, status.HTTP_200_OK

        return _idempotent_response(
            request,
            control,
            "case_update",
            apply_write,
            target_type="case",
            target_id=pk,
        )


def _case_edit_payload(case):
    patient = getattr(case, "patient", None)

    def iso(value):
        return value.isoformat() if value else None

    return {
        "id": case.id,
        "base_updated_at": case.updated_at.isoformat(),
        "patient_mode": "existing",
        "selected_patient": case.patient_id,
        "use_temporary_uhid": bool(getattr(patient, "is_temporary_id", False)),
        "uhid": case.uhid,
        "prefix": case.prefix,
        "first_name": case.first_name,
        "last_name": case.last_name,
        "gender": case.gender,
        "blood_group": case.blood_group,
        "date_of_birth": iso(case.date_of_birth),
        "place": case.place,
        "age": case.age,
        "phone_number": case.phone_number,
        "alternate_phone_number": case.alternate_phone_number,
        "category": case.category_id,
        "subcategory": case.subcategory,
        "status": case.status,
        "diagnosis": case.diagnosis,
        "referred_by": case.referred_by,
        "notes": case.notes,
        "high_risk": case.high_risk,
        "ncd_flags": case.ncd_flags or [],
        "anc_high_risk_reasons": case.anc_high_risk_reasons or [],
        "rch_number": case.rch_number,
        "rch_bypass": case.rch_bypass,
        "lmp": iso(case.lmp),
        "edd": iso(case.edd),
        "usg_edd": iso(case.usg_edd),
        "surgical_pathway": case.surgical_pathway,
        "surgery_done": case.surgery_done,
        "surgery_date": iso(case.surgery_date),
        "review_frequency": case.review_frequency,
        "review_date": iso(case.review_date),
        "gravida": case.gravida,
        "para": case.para,
        "abortions": case.abortions,
        "living": case.living,
        "ftnd": case.ftnd,
        "lscs": case.lscs,
    }


class CaseEditFormView(APIView):
    """Prefill + metadata for the mobile case-edit wizard."""

    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_case_edit_form_retrieve",
        responses={200: contract.CaseEditFormResponseSerializer, 404: contract.ErrorResponseSerializer},
    )
    def get(self, request, pk):
        case = get_object_or_404(
            _accessible_case_queryset(
                request.user,
                Case.objects.select_related("category", "patient"),
            ),
            pk=pk,
        )
        return Response(
            {
                "can_edit": has_capability(request.user, "case_edit"),
                "categories": _category_metadata_payload(),
                "prefixes": _choice_payload(CasePrefix.choices),
                "blood_groups": _choice_payload(BloodGroup.choices),
                "genders": _choice_payload(Gender.choices),
                "ncd_flags": _choice_payload(NonCommunicableDisease.choices),
                "anc_high_risk_reasons": _choice_payload(AncHighRiskReason.choices),
                "surgical_pathways": _choice_payload(SurgicalPathway.choices),
                "review_frequencies": _choice_payload(ReviewFrequency.choices),
                "case": _case_edit_payload(case),
            }
        )


IDEMPOTENCY_RECEIPT_TTL = timedelta(days=7)
IDEMPOTENT_OPERATION_CAPABILITIES = {
    "case_create": "case_create",
    "task_create": "task_create",
    "task_complete": "task_edit",
    "call_outcome": "note_add",
    "vitals_create": "task_edit",
    "case_update": "case_edit",
    "task_update": "task_edit",
    "vitals_update": "task_edit",
}

PATCH_CONTROL_FIELDS = {"client_write_id", "base_updated_at", "base_values"}


def _optimistic_patch_conflicts(*, current_values, request_data, base_values, base_updated_at, updated_at):
    if base_updated_at > updated_at:
        return ["base_updated_at"]
    touched_fields = [key for key in request_data if key not in PATCH_CONTROL_FIELDS]
    conflicts = []
    for field in touched_fields:
        if field not in current_values or field not in base_values:
            conflicts.append(field)
            continue
        current = _json_safe_payload(current_values[field])
        base = _json_safe_payload(base_values[field])
        if current != base:
            conflicts.append(field)
    return sorted(set(conflicts))


def _optimistic_conflict_response(fields):
    return {
        "code": "edit_conflict",
        "message": "One or more edited fields changed since the supplied base revision.",
        "errors": {field: ["Refresh this field before retrying."] for field in fields},
    }, status.HTTP_409_CONFLICT


def _idempotent_response(
    request,
    serializer,
    operation,
    apply_write,
    *,
    target_type,
    target_id="",
):
    client_write_id = serializer.validated_data.get("client_write_id", "").strip()
    if not client_write_id:
        with transaction.atomic():
            locked_user = _lock_mobile_authorization_context(request.user)
            request.user = locked_user
            _authorize_idempotent_target(locked_user, operation, target_type, target_id, lock=True)
            payload, response_status = apply_write()
            return Response(payload, status=response_status)

    binding = _idempotency_binding(request, operation, target_type, target_id)
    receipt_key = _idempotency_key_digest(client_write_id)
    with transaction.atomic():
        purge_expired_mobile_receipts()
        locked_user = _lock_mobile_authorization_context(request.user)
        request.user = locked_user
        _authorize_idempotent_target(locked_user, operation, target_type, target_id, lock=True)
        dataset_state, _ = MobileDatasetState.objects.select_for_update().get_or_create(pk=1)
        binding["authorization_hash"] = _authorization_hash(locked_user)
        binding["dataset_epoch"] = dataset_state.epoch

        receipt = MobileWriteReceipt.objects.select_for_update().filter(
            user=locked_user,
            client_write_id=receipt_key,
        ).first()
        if receipt and receipt.expires_at <= timezone.now():
            receipt.delete()
            receipt = None
        if receipt:
            mismatch = _idempotency_binding_mismatch(receipt, binding)
            if mismatch:
                return _idempotency_mismatch_response()
            return _replay_receipt(receipt, locked_user)

        receipt = MobileWriteReceipt.objects.create(
            user=locked_user,
            client_write_id=receipt_key,
            operation=operation,
            target_type=target_type,
            target_id=str(target_id or ""),
            payload_hash=binding["payload_hash"],
            authorization_hash=binding["authorization_hash"],
            dataset_epoch=binding["dataset_epoch"],
            status=MobileWriteReceipt.STATUS_PENDING,
            expires_at=timezone.now() + IDEMPOTENCY_RECEIPT_TTL,
        )
        payload, response_status = apply_write()
        result_type, result_id = _receipt_result(operation, target_id, payload)
        receipt.status = (
            MobileWriteReceipt.STATUS_APPLIED
            if response_status < 400
            else MobileWriteReceipt.STATUS_FAILED
        )
        receipt.response_status = response_status
        receipt.response_metadata = {
            "message": str(payload.get("message", ""))[:240]
            if isinstance(payload, dict)
            else "",
        }
        if isinstance(payload, dict):
            mobile_outcome = str((payload.get("call_log") or {}).get("mobile_outcome", ""))[:32]
            if mobile_outcome:
                receipt.response_metadata["mobile_outcome"] = mobile_outcome
        receipt.result_type = result_type
        receipt.result_id = str(result_id or "")
        receipt.save(
            update_fields=[
                "status",
                "response_status",
                "response_metadata",
                "result_type",
                "result_id",
                "updated_at",
            ]
        )
        return Response(payload, status=response_status)


def _idempotent_replay_response(
    request,
    serializer,
    operation,
    *,
    target_type,
    target_id="",
):
    client_write_id = serializer.validated_data.get("client_write_id", "").strip()
    if not client_write_id:
        return None
    binding = _idempotency_binding(request, operation, target_type, target_id)
    receipt_key = _idempotency_key_digest(client_write_id)
    with transaction.atomic():
        purge_expired_mobile_receipts()
        locked_user = _lock_mobile_authorization_context(request.user)
        request.user = locked_user
        _authorize_idempotent_target(locked_user, operation, target_type, target_id, lock=True)
        dataset_state, _ = MobileDatasetState.objects.select_for_update().get_or_create(pk=1)
        receipt = MobileWriteReceipt.objects.select_for_update().filter(
            user=locked_user,
            client_write_id=receipt_key,
        ).first()
        if not receipt:
            return None
        if receipt.expires_at <= timezone.now():
            receipt.delete()
            return None
        binding["authorization_hash"] = _authorization_hash(locked_user)
        binding["dataset_epoch"] = dataset_state.epoch
        if _idempotency_binding_mismatch(receipt, binding):
            return _idempotency_mismatch_response()
        return _replay_receipt(receipt, locked_user)


def _idempotency_binding(request, operation, target_type, target_id):
    return {
        "operation": operation,
        "target_type": target_type,
        "target_id": str(target_id or ""),
        "payload_hash": _canonical_payload_hash(request.data),
    }


def _idempotency_key_digest(client_write_id):
    return salted_hmac("api.mobile_write_receipt", client_write_id).hexdigest()


def _lock_mobile_authorization_context(user):
    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    UserSecurityState.objects.select_for_update().get_or_create(user=locked_user)
    through = get_user_model().groups.through
    list(
        through.objects.select_for_update()
        .filter(user_id=locked_user.pk)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    role_names = list(locked_user.groups.order_by("name").values_list("name", flat=True))
    list(RoleSetting.objects.select_for_update().filter(role_name__in=role_names).order_by("pk"))
    for cache_name in (
        "_medtrack_effective_role_policy",
        "_cached_role_settings",
        "_capability_cache",
        "_cached_group_names",
    ):
        if hasattr(locked_user, cache_name):
            delattr(locked_user, cache_name)
    return locked_user


def _canonical_payload_hash(data):
    if hasattr(data, "lists"):
        payload = {
            key: values if len(values) > 1 else values[0]
            for key, values in data.lists()
            if key != "client_write_id"
        }
    else:
        payload = {
            key: value
            for key, value in dict(data).items()
            if key != "client_write_id"
        }
    canonical = json.dumps(_json_safe_payload(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _authorization_hash(user):
    role_names = list(user.groups.order_by("name").values_list("name", flat=True))
    policy = effective_role_policy(user, fresh=True)
    role_binding_fields = [
        field.name
        for field in RoleSetting._meta.concrete_fields
        if field.name not in {"id", "role_name"}
    ]
    role_settings = list(
        RoleSetting.objects.filter(role_name__in=role_names)
        .order_by("role_name")
        .values("role_name", *role_binding_fields)
    )
    material = {
        "user_id": user.pk,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "auth_version": current_auth_version(user),
        "role_names": role_names,
        "effective_policy": {
            "case_data_scope": policy.case_data_scope,
            "can_access_call_queue": policy.can_access_call_queue,
            "can_intake_patient_lookup": policy.can_intake_patient_lookup,
            "capabilities": sorted(policy.capabilities),
            "matched_role_names": sorted(policy.role_names),
        },
        "roles": role_settings,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _authorize_idempotent_target(user, operation, target_type, target_id, *, lock=False):
    capability = IDEMPOTENT_OPERATION_CAPABILITIES[operation]
    if not user.is_active or not has_capability(user, capability):
        raise PermissionDenied("Current authorization does not permit this operation.")
    if target_type == "case":
        base = Case.objects.select_for_update() if lock else Case.objects.all()
        target = get_object_or_404(_accessible_case_queryset(user, base), pk=target_id)
        if lock:
            list(Task.objects.select_for_update().filter(case_id=target.pk).order_by("pk"))
        return target
    if target_type == "task":
        base = Task.objects.select_for_update() if lock else Task.objects.all()
        target = get_object_or_404(_accessible_task_queryset(user, base), pk=target_id)
        if lock:
            list(Task.objects.select_for_update().filter(case_id=target.case_id).order_by("pk"))
        return target
    if target_type == "vital":
        base = VitalEntry.objects.select_for_update() if lock else VitalEntry.objects.all()
        target = get_object_or_404(_accessible_vital_queryset(user, base), pk=target_id)
        if lock:
            list(Task.objects.select_for_update().filter(case_id=target.case_id).order_by("pk"))
        return target
    return None


def _idempotency_binding_mismatch(receipt, binding):
    return any(
        [
            receipt.operation != binding["operation"],
            receipt.target_type != binding["target_type"],
            receipt.target_id != binding["target_id"],
            receipt.payload_hash != binding["payload_hash"],
            receipt.authorization_hash != binding["authorization_hash"],
            receipt.dataset_epoch != binding["dataset_epoch"],
        ]
    )


def _idempotency_mismatch_response():
    return Response(
        {
            "code": "idempotency_mismatch",
            "message": (
                "client_write_id is already bound to a different operation, target, "
                "payload, authorization context, or dataset epoch."
            ),
        },
        status=status.HTTP_409_CONFLICT,
    )


def _receipt_result(operation, target_id, payload):
    if not isinstance(payload, dict):
        return "", ""
    if operation == "case_create":
        return "case", payload.get("case_id")
    if operation == "case_update":
        return "case", target_id
    if operation in {"task_create", "task_complete", "task_update"}:
        return "task", (payload.get("task") or {}).get("id") or target_id
    if operation == "call_outcome":
        return "call_log", (payload.get("call_log") or {}).get("id")
    if operation in {"vitals_create", "vitals_update"}:
        return "vital", (payload.get("vital") or {}).get("id")
    return "", ""


def _replay_receipt(receipt, user):
    if receipt.status == MobileWriteReceipt.STATUS_PENDING:
        return Response(
            {"code": "idempotency_in_progress", "message": "This write is still in progress."},
            status=status.HTTP_409_CONFLICT,
        )
    if receipt.status == MobileWriteReceipt.STATUS_FAILED:
        return Response(receipt.response_metadata, status=receipt.response_status)

    message = receipt.response_metadata.get("message", "")
    result_id = receipt.result_id
    if receipt.operation in {"case_create", "case_update"}:
        case = get_object_or_404(
            _accessible_case_queryset(user, Case.objects.select_related("category")),
            pk=result_id,
        )
        payload = {
            "message": message,
            "case_id": case.pk,
            "case": _mobile_case_payload(case, user=user),
        }
        if receipt.operation == "case_update":
            payload["editable_case"] = _case_edit_payload(case)
    elif receipt.operation in {"task_create", "task_complete", "task_update"}:
        task = get_object_or_404(
            _accessible_task_queryset(
                user,
                Task.objects.select_related("case", "case__category", "assigned_user"),
            ),
            pk=result_id,
        )
        payload = {
            "message": message,
            "task": _serialize_task(task, can_complete=has_capability(user, "task_edit")),
            "case": _mobile_case_payload(task.case, user=user),
        }
    elif receipt.operation == "call_outcome":
        call_log = get_object_or_404(
            CallLog.objects.select_related("case", "case__category").filter(
                case_id__in=_accessible_case_queryset(user).values("pk")
            ),
            pk=result_id,
        )
        payload = {
            "message": message,
            "call_log": {
                **_serialize_call_log_for_api(call_log),
                "mobile_outcome": receipt.response_metadata.get("mobile_outcome", ""),
            },
            "case": _mobile_case_payload(call_log.case, user=user),
        }
    elif receipt.operation in {"vitals_create", "vitals_update"}:
        vital = get_object_or_404(
            _accessible_vital_queryset(
                user,
                VitalEntry.objects.select_related("case", "case__category"),
            ),
            pk=result_id,
        )
        payload = {
            "message": message,
            "latest_vital_id": vital.pk,
            "vital": _serialize_vital(vital),
            "case": _mobile_case_payload(vital.case, user=user),
        }
    else:
        return _idempotency_mismatch_response()
    return Response(payload, status=receipt.response_status)


def _serialize_call_log_for_api(call_log):
    return {
        "id": call_log.id,
        "task_id": call_log.task_id,
        "outcome": call_log.outcome,
        "outcome_label": call_log.get_outcome_display(),
        "notes": call_log.notes,
        "client_event_at": _iso_datetime(call_log.client_event_at),
        "created_at": _iso_datetime(call_log.created_at),
    }


def _iso_datetime(value):
    return timezone.localtime(value).isoformat() if value else None


def _json_safe_payload(payload):
    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))


class TaskCompleteView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_task_complete",
        request=TaskCompleteSerializer,
        responses={
            200: contract.TaskWriteResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            404: contract.ErrorResponseSerializer,
            409: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response({"message": "You do not have permission to edit tasks."}, status=status.HTTP_403_FORBIDDEN)
        serializer = TaskCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def apply_write():
            task = get_object_or_404(
                _accessible_task_queryset(
                    request.user,
                    Task.objects.select_related("case", "case__category"),
                ),
                pk=pk,
            )
            success, message = _complete_task_inline(task, user=request.user)
            if not success:
                return {"message": message}, status.HTTP_400_BAD_REQUEST
            return {
                "message": message,
                "task": _serialize_task(task, can_complete=True),
                "case": _mobile_case_payload(task.case, user=request.user),
            }, status.HTTP_200_OK

        return _idempotent_response(
            request,
            serializer,
            "task_complete",
            apply_write,
            target_type="task",
            target_id=pk,
        )


def _task_edit_values(task):
    return {
        "title": task.title,
        "due_date": task.due_date.isoformat(),
        "status": task.status,
        "assigned_user": task.assigned_user_id,
        "task_type": task.task_type,
        "frequency_label": task.frequency_label,
        "notes": task.notes,
        "base_updated_at": task.updated_at.isoformat(),
    }


class TaskCreateView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_task_create",
        request=contract.TaskCreateRequestSerializer,
        responses={
            201: contract.TaskWriteResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            404: contract.ErrorResponseSerializer,
            409: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request, pk):
        if not has_capability(request.user, "task_create"):
            return Response(
                {"message": "You do not have permission to create tasks."},
                status=status.HTTP_403_FORBIDDEN,
            )
        write_serializer = ClientWriteSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        case = get_object_or_404(
            _accessible_case_queryset(request.user, Case.objects.select_related("category")),
            pk=pk,
        )
        form = TaskForm(request.data)
        if not form.is_valid():
            return Response(
                {"message": "Please fix the highlighted fields.", "errors": _form_errors(form)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def apply_write():
            task = form.save(commit=False)
            task.case = case
            task.created_by = request.user
            try:
                task.full_clean()
                task.save()
            except ValidationError as exc:
                return (
                    {"message": "Could not add task. Please check the inputs.", "errors": exc.message_dict},
                    status.HTTP_400_BAD_REQUEST,
                )
            create_case_activity(
                case=case,
                task=task,
                user=request.user,
                event_type=ActivityEventType.TASK,
                note=f"Task created: {task.title}",
            )
            return (
                {
                    "message": "Task added.",
                    "task": _serialize_task(task, can_complete=has_capability(request.user, "task_edit")),
                    "case": _mobile_case_payload(case, user=request.user),
                },
                status.HTTP_201_CREATED,
            )

        return _idempotent_response(
            request,
            write_serializer,
            "task_create",
            apply_write,
            target_type="case",
            target_id=pk,
        )


class TaskDetailView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_task_partial_update",
        request=contract.TaskPatchRequestSerializer,
        responses={
            200: contract.TaskWriteResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            404: contract.ErrorResponseSerializer,
            409: contract.ErrorResponseSerializer,
        },
    )
    def patch(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response(
                {"message": "You do not have permission to edit tasks."},
                status=status.HTTP_403_FORBIDDEN,
            )
        get_object_or_404(_accessible_task_queryset(request.user), pk=pk)
        control = PatchControlSerializer(data=request.data)
        control.is_valid(raise_exception=True)
        replay = _idempotent_replay_response(
            request,
            control,
            "task_update",
            target_type="task",
            target_id=pk,
        )
        if replay is not None:
            return replay

        def apply_write():
            task = get_object_or_404(
                _accessible_task_queryset(
                    request.user,
                    Task.objects.select_for_update(of=("self",)).select_related(
                        "case", "case__category", "assigned_user"
                    ),
                ),
                pk=pk,
            )
            current_values = _task_edit_values(task)
            conflicts = _optimistic_patch_conflicts(
                current_values=current_values,
                request_data=request.data,
                base_values=control.validated_data["base_values"],
                base_updated_at=control.validated_data["base_updated_at"],
                updated_at=task.updated_at,
            )
            if conflicts:
                return _optimistic_conflict_response(conflicts)
            previous_status = task.status
            requested_status = request.data.get("status")
            is_reopening = (
                previous_status == TaskStatus.COMPLETED
                and requested_status
                and requested_status != TaskStatus.COMPLETED
            )
            can_reopen = _can_reopen_tasks(request.user)
            if is_reopening and not can_reopen:
                return {
                    "code": "permission_denied",
                    "message": "You do not have permission to reopen completed tasks.",
                }, status.HTTP_403_FORBIDDEN
            data = {key: value for key, value in current_values.items() if key != "base_updated_at"}
            data.update(
                {key: value for key, value in request.data.items() if key not in PATCH_CONTROL_FIELDS}
            )
            form = TaskForm(data, instance=task, allow_reopen=can_reopen)
            if not form.is_valid():
                return {
                    "code": "invalid_request",
                    "message": "Please fix the highlighted fields.",
                    "errors": _form_errors(form),
                }, status.HTTP_400_BAD_REQUEST
            if is_reopening and form.cleaned_data.get("status") != TaskStatus.SCHEDULED:
                message = "Completed tasks can only be reopened to Scheduled."
                return {
                    "code": "invalid_request",
                    "message": message,
                    "errors": {"status": [message]},
                }, status.HTTP_400_BAD_REQUEST
            updated = form.save()
            if is_reopening:
                cancelled = _reopen_task_follow_up_cleanup(updated)
                note = f"Task reopened: {updated.title}"
                if cancelled:
                    label = "reminder" if cancelled == 1 else "reminders"
                    note = f"{note} ({cancelled} follow-up {label} cancelled)"
            else:
                note = f"Task updated: {updated.title} ({updated.status})"
            create_case_activity(
                case=updated.case,
                task=updated,
                user=request.user,
                event_type=ActivityEventType.TASK,
                note=note,
            )
            return {
                "message": "Task updated.",
                "task": _serialize_task(updated, can_complete=has_capability(request.user, "task_edit")),
                "case": _mobile_case_payload(updated.case, user=request.user),
            }, status.HTTP_200_OK

        return _idempotent_response(
            request,
            control,
            "task_update",
            apply_write,
            target_type="task",
            target_id=pk,
        )


class TaskNoteView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_task_note_create",
        request=contract.TaskNoteRequestSerializer,
        responses={
            200: contract.TaskWriteResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            404: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response(
                {"message": "You do not have permission to add task notes."},
                status=status.HTTP_403_FORBIDDEN,
            )
        task = get_object_or_404(
            _accessible_task_queryset(
                request.user,
                Task.objects.select_related("case", "case__category"),
            ),
            pk=pk,
        )
        note_text = (request.data.get("note") or "").strip()
        success, message = _save_task_note_inline(task, note_text=note_text, user=request.user)
        if not success:
            return Response({"message": message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "message": message,
                "task": _serialize_task(task, can_complete=has_capability(request.user, "task_edit")),
                "case": _mobile_case_payload(task.case, user=request.user),
            }
        )


class TaskFormMetadataView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_task_form_metadata_retrieve",
        responses={200: contract.TaskFormMetadataResponseSerializer},
    )
    def get(self, request):
        User = get_user_model()
        users = User.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        return Response(
            {
                "can_create": has_capability(request.user, "task_create"),
                "can_edit": has_capability(request.user, "task_edit"),
                "can_reopen": _can_reopen_tasks(request.user),
                "default_status": TaskStatus.SCHEDULED,
                "task_types": _choice_payload(TaskType.choices),
                "statuses": _choice_payload(TaskStatus.choices),
                "assignable_users": [
                    {"id": user.id, "name": _display_user_name(user) or user.get_username()}
                    for user in users
                ],
            }
        )


class VitalsDetailView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_vital_partial_update",
        request=contract.VitalsPatchRequestSerializer,
        responses={
            200: contract.VitalsWriteResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            404: contract.ErrorResponseSerializer,
            409: contract.ErrorResponseSerializer,
        },
    )
    def patch(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response(
                {"message": "You do not have permission to edit vitals."},
                status=status.HTTP_403_FORBIDDEN,
            )
        get_object_or_404(_accessible_vital_queryset(request.user), pk=pk)
        control = PatchControlSerializer(data=request.data)
        control.is_valid(raise_exception=True)
        replay = _idempotent_replay_response(
            request,
            control,
            "vitals_update",
            target_type="vital",
            target_id=pk,
        )
        if replay is not None:
            return replay
        serializer = VitalEntryUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def apply_write():
            vital = get_object_or_404(
                _accessible_vital_queryset(
                    request.user,
                    VitalEntry.objects.select_for_update(of=("self",)).select_related("case", "case__category"),
                ),
                pk=pk,
            )
            current_values = _vital_edit_values(vital)
            conflicts = _optimistic_patch_conflicts(
                current_values=current_values,
                request_data=request.data,
                base_values=control.validated_data["base_values"],
                base_updated_at=control.validated_data["base_updated_at"],
                updated_at=vital.updated_at,
            )
            if conflicts:
                return _optimistic_conflict_response(conflicts)
            updated, warning = serializer.update_vital(vital=vital, user=request.user)
            create_case_activity(
                case=updated.case,
                user=request.user,
                event_type=ActivityEventType.SYSTEM,
                note="Vitals entry updated.",
            )
            return {
                "message": warning or "Vitals updated.",
                "latest_vital_id": updated.id,
                "vital": _serialize_vital(updated),
                "case": _mobile_case_payload(updated.case, user=request.user),
            }, status.HTTP_200_OK

        return _idempotent_response(
            request,
            serializer,
            "vitals_update",
            apply_write,
            target_type="vital",
            target_id=pk,
        )


def _vital_edit_values(vital):
    return {
        "recorded_at": _iso_datetime(vital.recorded_at),
        "bp_systolic": vital.bp_systolic,
        "bp_diastolic": vital.bp_diastolic,
        "pr": vital.pr,
        "spo2": vital.spo2,
        "weight_kg": str(vital.weight_kg) if vital.weight_kg is not None else None,
        "hemoglobin": str(vital.hemoglobin) if vital.hemoglobin is not None else None,
        "base_updated_at": _iso_datetime(vital.updated_at),
    }


class CallOutcomeView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_call_outcome_create",
        request=CallOutcomeSerializer,
        responses={
            201: contract.CallWriteResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            404: contract.ErrorResponseSerializer,
            409: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request, pk):
        if not has_capability(request.user, "note_add"):
            return Response({"message": "You do not have permission to add call logs."}, status=status.HTTP_403_FORBIDDEN)
        replay_envelope = ClientWriteSerializer(data=request.data)
        replay_envelope.is_valid(raise_exception=True)
        replay = _idempotent_replay_response(
            request,
            replay_envelope,
            "call_outcome",
            target_type="case",
            target_id=pk,
        )
        if replay is not None:
            return replay
        serializer = CallOutcomeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def apply_write():
            case = get_object_or_404(
                _accessible_case_queryset(request.user, Case.objects.select_related("category")),
                pk=pk,
            )
            task = None
            task_id = serializer.validated_data.get("task_id")
            if task_id:
                task = get_object_or_404(case.tasks, pk=task_id)
            mobile_outcome = serializer.validated_data["outcome"]
            outcome = call_outcome_to_model_value(mobile_outcome)
            note = serializer.validated_data.get("note", "").strip()
            attempted_at = serializer.validated_data.get("attempted_at")
            if mobile_outcome == "attempted" and not note:
                note = "Mobile dialer opened; outcome was not confirmed."
            call_log = CallLog.objects.create(
                case=case,
                task=task,
                outcome=outcome,
                notes=note,
                staff_user=request.user,
                client_event_at=attempted_at,
            )
            create_case_activity(
                case=case,
                task=task,
                user=request.user,
                event_type=ActivityEventType.CALL,
                note=f"Call outcome logged: {call_log.get_outcome_display()}",
            )
            return {
                "message": "Call outcome logged.",
                "call_log": {
                    **_serialize_call_log_for_api(call_log),
                    "mobile_outcome": mobile_outcome,
                },
                "case": _mobile_case_payload(case, user=request.user),
            }, status.HTTP_201_CREATED

        return _idempotent_response(
            request,
            serializer,
            "call_outcome",
            apply_write,
            target_type="case",
            target_id=pk,
        )


class CaseVitalsView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_case_vital_create",
        request=VitalEntryCreateSerializer,
        responses={
            201: contract.VitalsWriteResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            404: contract.ErrorResponseSerializer,
            409: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response({"message": "You do not have permission to add vitals."}, status=status.HTTP_403_FORBIDDEN)
        replay_envelope = ClientWriteSerializer(data=request.data)
        replay_envelope.is_valid(raise_exception=True)
        replay = _idempotent_replay_response(
            request,
            replay_envelope,
            "vitals_create",
            target_type="case",
            target_id=pk,
        )
        if replay is not None:
            return replay
        serializer = VitalEntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def apply_write():
            case = get_object_or_404(
                _accessible_case_queryset(request.user, Case.objects.select_related("category")),
                pk=pk,
            )
            vital, warning = serializer.create_vital(case=case, user=request.user)
            create_case_activity(
                case=case,
                user=request.user,
                event_type=ActivityEventType.SYSTEM,
                note="Vitals entry recorded.",
            )
            return {
                "message": warning or "Vitals recorded.",
                "latest_vital_id": vital.id,
                "vital": _serialize_vital(vital),
                "case": _mobile_case_payload(case, user=request.user),
            }, status.HTTP_201_CREATED

        return _idempotent_response(
            request,
            serializer,
            "vitals_create",
            apply_write,
            target_type="case",
            target_id=pk,
        )


class VitalsThresholdsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="mobile_vitals_thresholds_retrieve",
        responses={200: contract.VitalsThresholdsResponseSerializer},
    )
    def get(self, request):
        return Response(vitals_thresholds_payload())


class DeviceTokenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="mobile_device_token_register",
        request=DeviceTokenSerializer,
        responses={
            200: contract.DeviceTokenResponseSerializer,
            201: contract.DeviceTokenResponseSerializer,
            400: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data["token"]
        defaults = {
            "user": request.user,
            "platform": serializer.validated_data.get("platform") or "android",
            "app_version": serializer.validated_data.get("app_version", ""),
            "device_label": serializer.validated_data.get("device_label", ""),
            "is_active": True,
            "last_seen_at": timezone.now(),
        }
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            device, created = MobileDeviceToken.objects.update_or_create(token=token, defaults=defaults)
            retained_ids = list(
                MobileDeviceToken.objects.filter(user=request.user, is_active=True)
                .order_by("-last_seen_at", "-updated_at", "-pk")
                .values_list("pk", flat=True)[:3]
            )
            MobileDeviceToken.objects.filter(user=request.user, is_active=True).exclude(
                pk__in=retained_ids
            ).update(is_active=False)
        return Response(
            {
                "id": device.id,
                "created": created,
                "platform": device.platform,
                "app_version": device.app_version,
                "device_label": device.device_label,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def _mobile_authorization_scope_hash(user):
    # Bind opaque cursors to the user's policy/authentication version, while
    # deliberately excluding the current object-id set. Object authorization is
    # queried again on every page, so an assignment revocation can purge the row
    # and safely continue the same snapshot instead of turning the cursor into a
    # denial-of-service boundary.
    return _authorization_hash(user)


def _notification_cursor_point(payload, field_name):
    point = payload.get(field_name)
    if not isinstance(point, dict):
        raise CursorValidationError("Invalid notification cursor position.")
    created_at = parse_datetime(str(point.get("created_at") or ""))
    try:
        row_id = int(point.get("id"))
    except (TypeError, ValueError) as exc:
        raise CursorValidationError("Invalid notification cursor position.") from exc
    if created_at is None or timezone.is_naive(created_at) or row_id < 1:
        raise CursorValidationError("Invalid notification cursor position.")
    return created_at, row_id


def _notification_cursor_value(notification):
    return {
        "created_at": notification.created_at.isoformat(),
        "id": notification.id,
    }


def _serialize_notification(notification):
    title, body, channel = GENERIC_NOTIFICATION_COPY[notification.notification_type]
    return {
        "id": notification.id,
        "event_id": str(notification.event_id),
        "type": notification.notification_type,
        "title": title,
        "body": body,
        "case_id": notification.case_id,
        "task_id": notification.task_id,
        "payload": {
            "event_id": str(notification.event_id),
            "type": notification.notification_type,
            "channel": channel,
        },
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
    }


class NotificationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="mobile_notifications_snapshot",
        parameters=[
            OpenApiParameter("type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("unread_only", OpenApiTypes.BOOL, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("cursor", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter(
                "page_size",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                required=False,
                description="Default 50; maximum 100.",
            ),
        ],
        responses={
            200: contract.NotificationsResponseSerializer,
            400: contract.ErrorResponseSerializer,
        },
    )
    def get(self, request):
        if "page" in request.GET:
            return Response(
                {"code": "page_not_supported", "message": "Use the opaque notification cursor."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            page_size = int(request.GET.get("page_size", 50))
        except (TypeError, ValueError):
            page_size = 0
        if not 1 <= page_size <= 100:
            return Response(
                {"code": "invalid_page_size", "message": "page_size must be between 1 and 100."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notification_type = request.GET.get("type", "").strip()
        valid_types = {value for value, _ in MobileNotification._meta.get_field("notification_type").choices}
        if notification_type and notification_type not in valid_types:
            return Response(
                {"code": "invalid_notification_type", "message": "Unknown notification type."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        unread_value = request.GET.get("unread_only", "").strip().lower()
        if unread_value in {"", "0", "false", "no"}:
            unread_only = False
        elif unread_value in {"1", "true", "yes"}:
            unread_only = True
        else:
            return Response(
                {"code": "invalid_unread_filter", "message": "unread_only must be true or false."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        binding = {
            "type": notification_type,
            "unread_only": unread_only,
            "page_size": page_size,
            "order": ["-created_at", "-id"],
        }
        with transaction.atomic():
            dataset_state, _ = MobileDatasetState.objects.select_for_update().get_or_create(pk=1)
            purge_expired_mobile_notifications()
            purge_stale_notifications_for_user(request.user)
            notification_state = notification_epoch_for_user(request.user, lock=True)
            authorization_scope = _mobile_authorization_scope_hash(request.user)
            cursor_context = {
                "actor_id": request.user.pk,
                "account_id": request.user.pk,
                "scope": role_data_scope_payload(request.user),
                "auth_version": current_auth_version(request.user),
                "dataset_epoch": str(notification_state.epoch),
                "global_dataset_epoch": str(dataset_state.epoch),
                "authorization_scope": authorization_scope,
            }
            queryset = authorized_notification_queryset(request.user).select_related("case", "task")
            if notification_type:
                queryset = queryset.filter(notification_type=notification_type)
            if unread_only:
                queryset = queryset.filter(read_at__isnull=True)
            queryset = queryset.order_by("-created_at", "-id")

            cursor_token = request.GET.get("cursor", "").strip()
            try:
                if cursor_token:
                    cursor_payload = decode_cursor(
                        cursor_token,
                        user=request.user,
                        kind="notification_snapshot",
                        binding=binding,
                        context=cursor_context,
                    )
                    snapshot_created_at, snapshot_id = _notification_cursor_point(
                        cursor_payload, "snapshot"
                    )
                    position_created_at, position_id = _notification_cursor_point(
                        cursor_payload, "position"
                    )
                else:
                    boundary = queryset.first()
                    if boundary is None:
                        return Response(
                            {
                                "dataset_epoch": str(notification_state.epoch),
                                "next_cursor": None,
                                "results": [],
                            }
                        )
                    snapshot_created_at, snapshot_id = boundary.created_at, boundary.id
                    position_created_at = position_id = None
            except CursorValidationError as exc:
                return Response(
                    {"code": "invalid_cursor", "message": str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(
                Q(created_at__lt=snapshot_created_at)
                | Q(created_at=snapshot_created_at, id__lte=snapshot_id)
            )
            if position_created_at is not None:
                queryset = queryset.filter(
                    Q(created_at__lt=position_created_at)
                    | Q(created_at=position_created_at, id__lt=position_id)
                )

            rows = list(queryset[: page_size + 1])
            page = rows[:page_size]
            next_cursor = None
            if len(rows) > page_size:
                next_cursor = encode_cursor(
                    user=request.user,
                    kind="notification_snapshot",
                    binding=binding,
                    context=cursor_context,
                    snapshot={"created_at": snapshot_created_at.isoformat(), "id": snapshot_id},
                    position=_notification_cursor_value(page[-1]),
                )
            return Response(
                {
                    "dataset_epoch": str(notification_state.epoch),
                    "next_cursor": next_cursor,
                    "results": [_serialize_notification(item) for item in page],
                }
            )


class NotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="mobile_notification_mark_read",
        request=None,
        responses={
            200: contract.NotificationReadResponseSerializer,
            404: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request, pk):
        purge_stale_notifications_for_user(request.user)
        notification = authorized_notification_queryset(request.user).filter(pk=pk).first()
        if notification is None:
            # Return a normal 404 response instead of raising after the purge.
            # With ATOMIC_REQUESTS an exception would roll back the revocation
            # delete and leave the stale PHI-bearing row behind.
            return Response(
                {"code": "not_found", "message": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(
            {
                "id": notification.id,
                "read_at": notification.read_at.isoformat(),
                "message": "Notification marked read.",
            }
        )


def _category_metadata_payload():
    categories = list(DepartmentConfig.objects.order_by("name"))
    theme_category_colors = build_theme_category_colors(categories)
    return [
        {
            "id": category.id,
            "name": category.name,
            "icon_path": _dashboard_category_icon_path(category.name),
            "theme": resolve_category_theme(theme_category_colors, category),
            "subcategories": [
                {
                    "value": value,
                    "label": label,
                    "icon_path": _dashboard_subcategory_icon_path(value),
                }
                for value, label in case_subcategory_choices_for_category_name(category.name)
            ],
        }
        for category in categories
    ]


def _choice_payload(choices):
    return [{"value": value, "label": str(label)} for value, label in choices]


class CategoryMetadataView(APIView):
    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_category_metadata_retrieve",
        responses={200: contract.CategoriesResponseSerializer},
    )
    def get(self, request):
        return Response({"categories": _category_metadata_payload()})


class CaseFormMetadataView(APIView):
    """Everything the mobile case-creation wizard needs to render its menus."""

    permission_classes = [HasMobileCaseAccess]

    @extend_schema(
        operation_id="mobile_case_form_metadata_retrieve",
        responses={200: contract.CaseFormMetadataResponseSerializer},
    )
    def get(self, request):
        return Response(
            {
                "can_create": has_capability(request.user, "case_create"),
                "categories": _category_metadata_payload(),
                "prefixes": _choice_payload(CasePrefix.choices),
                "blood_groups": _choice_payload(BloodGroup.choices),
                "genders": _choice_payload(Gender.choices),
                "ncd_flags": _choice_payload(NonCommunicableDisease.choices),
                "anc_high_risk_reasons": _choice_payload(AncHighRiskReason.choices),
                "surgical_pathways": _choice_payload(SurgicalPathway.choices),
                "review_frequencies": _choice_payload(ReviewFrequency.choices),
            }
        )


def _serialize_patient_row(patient):
    return {
        "id": patient.id,
        "uhid": patient.uhid,
        "name": patient.patient_name or patient.full_name,
    }


def _normalize_patient_search_query(query):
    collapsed = " ".join(query.split())
    if re.fullmatch(r"[0-9().+\-\s]+", collapsed):
        digits = re.sub(r"\D", "", collapsed)
        if len(digits) == 10:
            return digits, digits
    return collapsed.casefold(), None


def _patient_search_class(normalized_query, normalized_phone):
    if normalized_phone:
        return "phone_exact"
    if normalized_query.upper().startswith(("UH-", "TMP-", "TN-")):
        return "uhid_prefix"
    return "name_or_uhid_prefix"


def _safe_search_length(request):
    raw_query = request.data.get("query", "") if isinstance(request.data, dict) else ""
    return len(" ".join(raw_query.split())) if isinstance(raw_query, str) else 0


def _record_patient_search_audit(
    request,
    *,
    search_class,
    normalized_length,
    result_count,
    denied=False,
):
    return record_audit_event(
        category=AuditEvent.Category.DATA,
        action="patient.search_attempt",
        outcome=AuditEvent.Outcome.DENIED if denied else AuditEvent.Outcome.SUCCESS,
        actor=request.user,
        request=request,
        object_type="patient_directory",
        metadata={
            "search_class": search_class,
            "normalized_length": normalized_length,
            "result_count": result_count,
            "scope": role_data_scope_payload(request.user),
        },
    )


class PatientSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [DatabaseSearchThrottle]
    database_throttle_scope = "api_patient_search"
    search_audit_action = "patient.search_attempt"
    search_object_type = "patient_directory"

    @extend_schema(
        operation_id="mobile_patient_search_create",
        request=contract.PatientSearchRequestSerializer,
        responses={
            200: contract.PatientSearchResponseSerializer,
            400: contract.ErrorResponseSerializer,
            429: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request):
        scope = role_data_scope_payload(request.user)
        if not (can_access_case_data(request.user) or scope.get("intake_patient_lookup")):
            _record_patient_search_audit(
                request,
                search_class="permission_denied",
                normalized_length=_safe_search_length(request),
                result_count=0,
                denied=True,
            )
            return Response(
                {"code": "search_denied", "message": "Patient search is not permitted."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.query_params:
            _record_patient_search_audit(
                request,
                search_class="url_parameters_rejected",
                normalized_length=0,
                result_count=0,
                denied=True,
            )
            return Response(
                {
                    "code": "search_parameters_in_url",
                    "message": "Patient search parameters must be sent in the JSON body.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PatientSearchSerializer(data=request.data)
        if not serializer.is_valid():
            raw_query = request.data.get("query", "")
            normalized_invalid = " ".join(raw_query.split()).casefold() if isinstance(raw_query, str) else ""
            normalized_invalid, invalid_phone = _normalize_patient_search_query(normalized_invalid)
            _record_patient_search_audit(
                request,
                search_class=_patient_search_class(normalized_invalid, invalid_phone),
                normalized_length=len(normalized_invalid),
                result_count=0,
                denied=True,
            )
            return Response(
                {
                    "code": "invalid_search_request",
                    "message": "Patient search request is invalid.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        query = serializer.validated_data["query"]
        normalized_query, normalized_phone = _normalize_patient_search_query(query)
        page_size = serializer.validated_data["page_size"]
        binding = {
            "query": normalized_query,
            "phone": normalized_phone,
            "search_class": _patient_search_class(normalized_query, normalized_phone),
            "page_size": page_size,
            "order": ["uhid", "id"],
        }
        dataset_state, _ = MobileDatasetState.objects.get_or_create(pk=1)
        cursor_context = {
            "actor_id": request.user.pk,
            "account_id": request.user.pk,
            "scope": role_data_scope_payload(request.user),
            "auth_version": current_auth_version(request.user),
            "dataset_epoch": str(dataset_state.epoch),
            "authorization_scope": _mobile_authorization_scope_hash(request.user),
        }
        cursor_token = serializer.validated_data.get("cursor")
        try:
            if cursor_token:
                cursor_payload = decode_cursor(
                    cursor_token,
                    user=request.user,
                    kind="patient_search",
                    binding=binding,
                    context=cursor_context,
                )
                position = cursor_payload["position"]
                position_uhid = str(position.get("uhid") or "")
                position_id = int(position.get("id"))
                snapshot_max_id = int(cursor_payload.get("snapshot", {}).get("max_id"))
                if not position_uhid or position_id < 1 or snapshot_max_id < 1:
                    raise CursorValidationError("Invalid patient search cursor position.")
            else:
                position_uhid = ""
                position_id = 0
                snapshot_max_id = 0
        except (CursorValidationError, KeyError, TypeError, ValueError) as exc:
            _record_patient_search_audit(
                request,
                search_class="invalid_cursor",
                normalized_length=len(normalized_query),
                result_count=0,
                denied=True,
            )
            return Response(
                {"code": "invalid_cursor", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = _patient_search_queryset(
            "",
            user=request.user,
            allow_intake_lookup=bool(scope.get("intake_patient_lookup")),
        )
        if normalized_phone:
            prefix_filters = Q(phone_number=normalized_phone) | Q(
                alternate_phone_number=normalized_phone
            )
        else:
            prefix_filters = (
                Q(uhid__istartswith=normalized_query)
                | Q(first_name__istartswith=normalized_query)
                | Q(last_name__istartswith=normalized_query)
                | Q(patient_name__istartswith=normalized_query)
            )
        queryset = queryset.filter(prefix_filters).order_by("uhid", "id")
        if not cursor_token:
            snapshot_max_id = queryset.aggregate(max_id=Max("id"))["max_id"] or 0
        queryset = queryset.filter(id__lte=snapshot_max_id)
        if position_uhid:
            queryset = queryset.filter(
                Q(uhid__gt=position_uhid) | Q(uhid=position_uhid, id__gt=position_id)
            )

        rows = list(queryset[: page_size + 1])
        page = rows[:page_size]
        next_cursor = None
        if len(rows) > page_size:
            next_cursor = encode_cursor(
                user=request.user,
                kind="patient_search",
                binding=binding,
                context=cursor_context,
                position={"uhid": page[-1].uhid, "id": page[-1].id},
                snapshot={"max_id": snapshot_max_id},
            )
        _record_patient_search_audit(
            request,
            search_class=_patient_search_class(normalized_query, normalized_phone),
            normalized_length=len(normalized_query),
            result_count=len(page),
        )
        return Response(
            {
                "next_cursor": next_cursor,
                "results": [_serialize_patient_row(patient) for patient in page],
            }
        )


def _record_case_search_audit(request, *, search_class, normalized_length, result_count, denied=False):
    return record_audit_event(
        category=AuditEvent.Category.DATA,
        action="case.search_attempt",
        outcome=AuditEvent.Outcome.DENIED if denied else AuditEvent.Outcome.SUCCESS,
        actor=request.user,
        request=request,
        object_type="case_directory",
        metadata={
            "search_class": search_class,
            "normalized_length": normalized_length,
            "result_count": result_count,
            "scope": role_data_scope_payload(request.user),
        },
    )


class CaseSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [DatabaseSearchThrottle]
    database_throttle_scope = "api_case_search"
    search_audit_action = "case.search_attempt"
    search_object_type = "case_directory"

    @extend_schema(
        operation_id="mobile_case_search_create",
        request=contract.CaseSearchRequestSerializer,
        responses={
            200: contract.CaseSearchResponseSerializer,
            400: contract.ErrorResponseSerializer,
            403: contract.ErrorResponseSerializer,
            429: contract.ErrorResponseSerializer,
        },
    )
    def post(self, request):
        if not can_access_case_data(request.user):
            _record_case_search_audit(
                request,
                search_class="permission_denied",
                normalized_length=_safe_search_length(request),
                result_count=0,
                denied=True,
            )
            return Response(
                {"code": "search_denied", "message": "Case search is not permitted."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.query_params:
            _record_case_search_audit(
                request,
                search_class="url_parameters_rejected",
                normalized_length=0,
                result_count=0,
                denied=True,
            )
            return Response(
                {"code": "search_parameters_in_url", "message": "Case search parameters must be sent in the JSON body."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = CaseSearchSerializer(data=request.data)
        if not serializer.is_valid():
            raw_query = request.data.get("query", "")
            normalized = " ".join(raw_query.split()).casefold() if isinstance(raw_query, str) else ""
            normalized, phone = _normalize_patient_search_query(normalized)
            _record_case_search_audit(
                request,
                search_class=_patient_search_class(normalized, phone),
                normalized_length=len(normalized),
                result_count=0,
                denied=True,
            )
            return Response(
                {"code": "invalid_search_request", "message": "Case search request is invalid.", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_query, normalized_phone = _normalize_patient_search_query(serializer.validated_data["query"])
        page_size = serializer.validated_data["page_size"]
        search_class = _patient_search_class(normalized_query, normalized_phone)
        filter_values = {
            "bucket": serializer.validated_data["bucket"],
            "assigned_to": serializer.validated_data.get("assigned_to") or _default_assigned_to_scope(request.user),
            "scope_context": serializer.validated_data.get("scope_context", ""),
            "category": sorted(set(serializer.validated_data.get("category") or [])),
            "subcategory": sorted(set(serializer.validated_data.get("subcategory") or [])),
        }
        binding = {
            "query": normalized_query,
            "phone": normalized_phone,
            "search_class": search_class,
            "page_size": page_size,
            "filters": filter_values,
            "order": ["next_due", "-updated_at", "id"],
        }
        dataset_state, _ = MobileDatasetState.objects.get_or_create(pk=1)
        context = {
            "actor_id": request.user.pk,
            "account_id": request.user.pk,
            "scope": role_data_scope_payload(request.user),
            "auth_version": current_auth_version(request.user),
            "dataset_epoch": str(dataset_state.epoch),
            "authorization_scope": _mobile_authorization_scope_hash(request.user),
        }
        cursor_token = serializer.validated_data.get("cursor")
        try:
            if cursor_token:
                payload = decode_cursor(
                    cursor_token,
                    user=request.user,
                    kind="case_search",
                    binding=binding,
                    context=context,
                )
                position_uhid = str(payload["position"].get("uhid") or "")
                position_id = int(payload["position"].get("id"))
                position_updated_at = parse_datetime(str(payload["position"].get("updated_at") or ""))
                raw_next_due = payload["position"].get("next_due")
                position_next_due = date.fromisoformat(raw_next_due) if raw_next_due else None
                snapshot_max_id = int(payload.get("snapshot", {}).get("max_id"))
                if position_id < 1 or snapshot_max_id < 1 or position_updated_at is None:
                    raise CursorValidationError("Invalid case search cursor position.")
            else:
                position_id = 0
                position_updated_at = None
                position_next_due = None
                snapshot_max_id = 0
        except (CursorValidationError, KeyError, TypeError, ValueError) as exc:
            _record_case_search_audit(
                request,
                search_class="invalid_cursor",
                normalized_length=len(normalized_query),
                result_count=0,
                denied=True,
            )
            return Response(
                {"code": "invalid_cursor", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = _accessible_case_queryset(
            request.user,
            Case.objects.select_related("category").filter(status=CaseStatus.ACTIVE),
        )
        if not cursor_token:
            snapshot_max_id = queryset.aggregate(max_id=Max("id"))["max_id"] or 0
        if normalized_phone:
            match = Q(phone_number=normalized_phone) | Q(alternate_phone_number=normalized_phone)
        else:
            match = (
                Q(uhid__istartswith=normalized_query)
                | Q(first_name__istartswith=normalized_query)
                | Q(last_name__istartswith=normalized_query)
                | Q(patient_name__istartswith=normalized_query)
            )
        base_queryset = _apply_case_search_body_filters(
            queryset.filter(match, id__lte=snapshot_max_id),
            request.user,
            filter_values,
            include_bucket=False,
        )
        stats = _counter_payload(base_queryset)
        queryset = _apply_case_search_body_filters(
            base_queryset,
            request.user,
            filter_values,
            include_bucket=True,
        ).annotate(
            next_due=Min(
                "tasks__due_date",
                filter=~Q(tasks__status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
            ),
        ).order_by("next_due", "-updated_at", "id").prefetch_related(
            Prefetch(
                "tasks",
                queryset=Task.objects.select_related("assigned_user").order_by("due_date", "id"),
                to_attr="prefetched_mobile_tasks",
            ),
            Prefetch(
                "vitals",
                queryset=VitalEntry.objects.order_by("-recorded_at", "-id"),
                to_attr="prefetched_mobile_vitals",
            ),
        )
        queryset = queryset.filter(id__lte=snapshot_max_id)
        if position_updated_at is not None:
            if position_next_due is None:
                queryset = queryset.filter(
                    (
                        Q(next_due__isnull=True)
                        & (
                            Q(updated_at__lt=position_updated_at)
                            | Q(updated_at=position_updated_at, id__gt=position_id)
                        )
                    )
                    | Q(next_due__isnull=False)
                )
            else:
                queryset = queryset.filter(
                    Q(next_due__gt=position_next_due)
                    | Q(next_due=position_next_due, updated_at__lt=position_updated_at)
                    | Q(
                        next_due=position_next_due,
                        updated_at=position_updated_at,
                        id__gt=position_id,
                    )
                )
        rows = list(queryset[: page_size + 1])
        page = rows[:page_size]
        next_cursor = None
        if len(rows) > page_size:
            next_cursor = encode_cursor(
                user=request.user,
                kind="case_search",
                binding=binding,
                context=context,
                position={
                    "next_due": page[-1].next_due.isoformat() if page[-1].next_due else None,
                    "updated_at": page[-1].updated_at.isoformat(),
                    "id": page[-1].id,
                },
                snapshot={"max_id": snapshot_max_id},
            )
        _record_case_search_audit(
            request,
            search_class=search_class,
            normalized_length=len(normalized_query),
            result_count=len(page),
        )
        today = timezone.localdate()
        category_colors = build_theme_category_colors([row.category for row in page if row.category_id])
        return Response(
            {
                "next_cursor": next_cursor,
                "stats": stats,
                "results": [
                    _serialize_case_row(row, user=request.user, today=today, theme_category_colors=category_colors)
                    for row in page
                ],
            }
        )
