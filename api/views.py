import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Max, Min, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from patients.models import (
    ActivityEventType,
    AncHighRiskReason,
    BloodGroup,
    CallLog,
    Case,
    CaseActivityLog,
    CasePrefix,
    CaseStatus,
    DepartmentConfig,
    Gender,
    NonCommunicableDisease,
    Patient,
    ReviewFrequency,
    SurgicalPathway,
    Task,
    TaskStatus,
    TaskType,
    VitalEntry,
    build_default_tasks,
    cancel_open_rch_reminders,
    case_subcategory_choices_for_category_name,
    ensure_rch_reminder_task,
    frequency_to_days,
    is_anc_case,
)
from patients.theme import build_theme_category_colors, resolve_category_theme
from patients.vitals_thresholds import vitals_thresholds_payload
from patients.forms import CaseForm, TaskForm
from patients.views import (
    CASE_CATEGORY_GROUP_FILTERS,
    _blood_pressure_display,
    _build_case_detail_json_payload,
    _build_latest_vitals_summary,
    _can_reopen_tasks,
    _complete_task_inline,
    _dashboard_category_icon_path,
    _dashboard_subcategory_icon_path,
    _display_user_name,
    _patient_search_queryset,
    _reopen_task_inline,
    _reschedule_task_inline,
    _reopen_task_follow_up_cleanup,
    _save_task_note_inline,
    _visible_case_queryset,
    _visible_task_queryset,
    can_access_case_data,
    create_case_activity,
    has_capability,
    is_doctor_admin,
)

from .models import MobileDeviceToken, MobileNotification, MobileWriteReceipt
from .permissions import HasMobileCaseAccess
from .serializers import (
    CallOutcomeSerializer,
    ClientWriteSerializer,
    DeviceTokenSerializer,
    LogoutSerializer,
    TaskCompleteSerializer,
    VitalEntryCreateSerializer,
    VitalEntryUpdateSerializer,
    call_outcome_to_model_value,
)


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
            }
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device_token = serializer.validated_data.get("device_token", "").strip()
        devices = MobileDeviceToken.objects.filter(user=request.user, is_active=True)
        if device_token:
            devices = devices.filter(token=device_token)
        deactivated_count = devices.update(is_active=False)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            return Response(
                {
                    "message": "Refresh token is invalid or already expired.",
                    "deactivated_devices": deactivated_count,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"message": "Logged out.", "deactivated_devices": deactivated_count},
            status=status.HTTP_200_OK,
        )


def _red_flag_query():
    return Q(high_risk=True) | ~Q(anc_high_risk_reasons=[]) | ~Q(ncd_flags=[])


def _case_search_query(raw_query):
    query = (raw_query or "").strip()
    if not query:
        return Q()
    return (
        Q(uhid__icontains=query)
        | Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(patient_name__icontains=query)
        | Q(phone_number__icontains=query)
        | Q(alternate_phone_number__icontains=query)
        | Q(place__icontains=query)
        | Q(diagnosis__icontains=query)
    )


def _default_assigned_to_scope(user):
    return "all" if is_doctor_admin(user) else "me"


def _apply_scope_filters(queryset, request, *, include_bucket=True):
    today = timezone.localdate()
    assigned_to = request.GET.get("assigned_to", _default_assigned_to_scope(request.user)).strip()
    if assigned_to == "me":
        queryset = queryset.filter(tasks__assigned_user=request.user)
    elif assigned_to not in {"all", ""}:
        queryset = queryset.none()

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

    search_query = _case_search_query(request.GET.get("q", ""))
    if search_query:
        queryset = queryset.filter(search_query)

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
        "can_complete": can_complete and task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED},
    }


def _serialize_vital(vital):
    return {
        "id": vital.id,
        "recorded_at": vital.recorded_at.isoformat(),
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

    def get(self, request):
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

    def post(self, request):
        if not has_capability(request.user, "case_create"):
            return Response(
                {"message": "You do not have permission to create cases."},
                status=status.HTTP_403_FORBIDDEN,
            )
        write_serializer = ClientWriteSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)

        form = CaseForm(data=request.data)
        form.actor = request.user
        form.instance.created_by = request.user
        if not form.is_valid():
            return Response(
                {"message": "Please fix the highlighted fields.", "errors": _form_errors(form)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def apply_write():
            with transaction.atomic():
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

        return _idempotent_response(request, write_serializer, "case_create", apply_write)


def _form_errors(form):
    return {
        field: [str(error) for error in errors]
        for field, errors in form.errors.items()
    }


class CaseDetailView(APIView):
    permission_classes = [HasMobileCaseAccess]

    def get(self, request, pk):
        case = get_object_or_404(_visible_case_queryset(Case.objects.select_related("category")), pk=pk)
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
                "created_at": log.created_at.isoformat(),
            }
            for log in case.call_logs.select_related("task").order_by("-created_at", "-id")[:20]
        ]
        return Response(payload)

    def patch(self, request, pk):
        if not has_capability(request.user, "case_edit"):
            return Response(
                {"message": "You do not have permission to edit cases."},
                status=status.HTTP_403_FORBIDDEN,
            )
        case = get_object_or_404(
            _visible_case_queryset(Case.objects.select_related("category", "patient")), pk=pk
        )
        old_status = case.status
        # The mobile wizard does not expose every patient identity field, so backfill the
        # ones it omits from the existing record. Without this, a mobile edit would submit a
        # full CaseForm without date_of_birth / alternate_phone_number and erase them.
        data = request.data.copy()
        if not data.get("date_of_birth") and case.date_of_birth:
            data["date_of_birth"] = case.date_of_birth.isoformat()
        if not data.get("alternate_phone_number") and case.alternate_phone_number:
            data["alternate_phone_number"] = case.alternate_phone_number
        form = CaseForm(data=data, instance=case)
        form.actor = request.user
        if not form.is_valid():
            return Response(
                {"message": "Please fix the highlighted fields.", "errors": _form_errors(form)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_status = form.cleaned_data.get("status") or old_status
        grey_list_cutoff = timezone.localdate() - timedelta(days=30)
        has_grey_tasks = case.tasks.exclude(status=TaskStatus.COMPLETED).filter(
            due_date__lt=grey_list_cutoff
        ).exists()
        if (
            has_grey_tasks
            and new_status in [CaseStatus.LOSS_TO_FOLLOW_UP, CaseStatus.ACTIVE]
            and not is_doctor_admin(request.user)
        ):
            message = "Only Doctor/Admin can set Grey List cases to Active or Loss to Follow-up."
            return Response(
                {"message": message, "errors": {"status": [message]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
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
        return Response(
            {
                "message": "Case updated.",
                "case_id": updated.id,
                "case": _mobile_case_payload(updated, user=request.user),
            }
        )


def _case_edit_payload(case):
    patient = getattr(case, "patient", None)

    def iso(value):
        return value.isoformat() if value else None

    return {
        "id": case.id,
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

    def get(self, request, pk):
        case = get_object_or_404(
            _visible_case_queryset(Case.objects.select_related("category", "patient")), pk=pk
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


def _idempotent_response(request, serializer, write_type, apply_write):
    client_write_id = serializer.validated_data.get("client_write_id", "").strip()
    if not client_write_id:
        payload, response_status = apply_write()
        return Response(payload, status=response_status)

    with transaction.atomic():
        receipt = MobileWriteReceipt.objects.select_for_update().filter(
            user=request.user,
            client_write_id=client_write_id,
        ).first()
        if receipt:
            return Response(receipt.response_payload, status=receipt.response_status)
        payload, response_status = apply_write()
        MobileWriteReceipt.objects.create(
            user=request.user,
            client_write_id=client_write_id,
            write_type=write_type,
            response_payload=_json_safe_payload(payload),
            response_status=response_status,
            status=MobileWriteReceipt.STATUS_APPLIED if response_status < 400 else MobileWriteReceipt.STATUS_FAILED,
        )
        return Response(payload, status=response_status)


def _json_safe_payload(payload):
    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))


class TaskCompleteView(APIView):
    permission_classes = [HasMobileCaseAccess]

    def post(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response({"message": "You do not have permission to edit tasks."}, status=status.HTTP_403_FORBIDDEN)
        serializer = TaskCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def apply_write():
            task = get_object_or_404(
                _visible_task_queryset(Task.objects.select_related("case", "case__category")),
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

        return _idempotent_response(request, serializer, "task_complete", apply_write)


def _task_form_partial_data(task, request):
    data = {
        "title": task.title,
        "due_date": task.due_date.isoformat(),
        "status": task.status,
        "assigned_user": task.assigned_user_id,
        "task_type": task.task_type,
        "frequency_label": task.frequency_label,
        "notes": task.notes,
    }
    for key in ("title", "due_date", "status", "assigned_user", "task_type", "frequency_label", "notes"):
        if key in request.data:
            data[key] = request.data.get(key)
    return data


class TaskCreateView(APIView):
    permission_classes = [HasMobileCaseAccess]

    def post(self, request, pk):
        if not has_capability(request.user, "task_create"):
            return Response(
                {"message": "You do not have permission to create tasks."},
                status=status.HTTP_403_FORBIDDEN,
            )
        write_serializer = ClientWriteSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        case = get_object_or_404(_visible_case_queryset(Case.objects.select_related("category")), pk=pk)
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

        return _idempotent_response(request, write_serializer, "task_create", apply_write)


class TaskDetailView(APIView):
    permission_classes = [HasMobileCaseAccess]

    def patch(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response(
                {"message": "You do not have permission to edit tasks."},
                status=status.HTTP_403_FORBIDDEN,
            )
        task = get_object_or_404(
            _visible_task_queryset(
                Task.objects.select_related("case", "case__category", "assigned_user")
            ),
            pk=pk,
        )
        previous_status = task.status
        requested_status = request.data.get("status")
        is_reopening = (
            previous_status == TaskStatus.COMPLETED
            and requested_status
            and requested_status != TaskStatus.COMPLETED
        )
        can_reopen = _can_reopen_tasks(request.user)
        if is_reopening and not can_reopen:
            return Response(
                {"message": "You do not have permission to reopen completed tasks."},
                status=status.HTTP_403_FORBIDDEN,
            )
        form = TaskForm(_task_form_partial_data(task, request), instance=task, allow_reopen=can_reopen)
        if not form.is_valid():
            return Response(
                {"message": "Please fix the highlighted fields.", "errors": _form_errors(form)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if is_reopening and form.cleaned_data.get("status") != TaskStatus.SCHEDULED:
            message = "Completed tasks can only be reopened to Scheduled."
            return Response(
                {"message": message, "errors": {"status": [message]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
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
        return Response(
            {
                "message": "Task updated.",
                "task": _serialize_task(updated, can_complete=has_capability(request.user, "task_edit")),
                "case": _mobile_case_payload(updated.case, user=request.user),
            }
        )


class TaskNoteView(APIView):
    permission_classes = [HasMobileCaseAccess]

    def post(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response(
                {"message": "You do not have permission to add task notes."},
                status=status.HTTP_403_FORBIDDEN,
            )
        task = get_object_or_404(
            _visible_task_queryset(Task.objects.select_related("case", "case__category")), pk=pk
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

    def patch(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response(
                {"message": "You do not have permission to edit vitals."},
                status=status.HTTP_403_FORBIDDEN,
            )
        vital = get_object_or_404(
            VitalEntry.objects.select_related("case", "case__category"), pk=pk
        )
        get_object_or_404(_visible_case_queryset(Case.objects.all()), pk=vital.case_id)
        serializer = VitalEntryUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated, warning = serializer.update_vital(vital=vital, user=request.user)
        create_case_activity(
            case=updated.case,
            user=request.user,
            event_type=ActivityEventType.SYSTEM,
            note="Vitals entry updated.",
        )
        return Response(
            {
                "message": warning or "Vitals updated.",
                "latest_vital_id": updated.id,
                "vital": _serialize_vital(updated),
                "case": _mobile_case_payload(updated.case, user=request.user),
            }
        )


class CallOutcomeView(APIView):
    permission_classes = [HasMobileCaseAccess]

    def post(self, request, pk):
        if not has_capability(request.user, "note_add"):
            return Response({"message": "You do not have permission to add call logs."}, status=status.HTTP_403_FORBIDDEN)
        serializer = CallOutcomeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def apply_write():
            case = get_object_or_404(_visible_case_queryset(Case.objects.select_related("category")), pk=pk)
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
            )
            if attempted_at:
                call_log.created_at = attempted_at
                call_log.save(update_fields=["created_at"])
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
                    "id": call_log.id,
                    "task_id": call_log.task_id,
                    "mobile_outcome": mobile_outcome,
                    "outcome": call_log.outcome,
                    "outcome_label": call_log.get_outcome_display(),
                    "notes": call_log.notes,
                    "created_at": call_log.created_at.isoformat(),
                },
                "case": _mobile_case_payload(case, user=request.user),
            }, status.HTTP_201_CREATED

        return _idempotent_response(request, serializer, "call_outcome", apply_write)


class CaseVitalsView(APIView):
    permission_classes = [HasMobileCaseAccess]

    def post(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return Response({"message": "You do not have permission to add vitals."}, status=status.HTTP_403_FORBIDDEN)
        serializer = VitalEntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def apply_write():
            case = get_object_or_404(_visible_case_queryset(Case.objects.select_related("category")), pk=pk)
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

        return _idempotent_response(request, serializer, "vitals_create", apply_write)


class VitalsThresholdsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(vitals_thresholds_payload())


class DeviceTokenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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
        device, created = MobileDeviceToken.objects.update_or_create(token=token, defaults=defaults)
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


class NotificationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = MobileNotification.objects.select_related("case", "task").filter(user=request.user)
        notification_type = request.GET.get("type", "").strip()
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        if request.GET.get("unread_only", "").lower() in {"1", "true", "yes"}:
            queryset = queryset.filter(read_at__isnull=True)
        paginator = MobilePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return Response(
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": [
                    {
                        "id": item.id,
                        "type": item.notification_type,
                        "title": item.title,
                        "body": item.body,
                        "case_id": item.case_id,
                        "task_id": item.task_id,
                        "payload": item.payload,
                        "read_at": item.read_at.isoformat() if item.read_at else None,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in page
                ],
            }
        )


class NotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(MobileNotification, pk=pk, user=request.user)
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

    def get(self, request):
        return Response({"categories": _category_metadata_payload()})


class CaseFormMetadataView(APIView):
    """Everything the mobile case-creation wizard needs to render its menus."""

    permission_classes = [HasMobileCaseAccess]

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
        "prefix": patient.prefix,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "gender": patient.gender,
        "gender_label": patient.get_gender_display() if patient.gender else "",
        "blood_group": patient.blood_group,
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "age": patient.age,
        "place": patient.place,
        "phone_number": patient.phone_number,
        "alternate_phone_number": patient.alternate_phone_number,
        "is_temporary_id": patient.is_temporary_id,
        "active_case_count": getattr(patient, "active_case_count", None),
        "total_case_count": getattr(patient, "total_case_count", None),
    }


class PatientSearchView(APIView):
    permission_classes = [HasMobileCaseAccess]

    def get(self, request):
        query = request.GET.get("q", "").strip()
        queryset = _patient_search_queryset(query)
        paginator = MobilePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return Response(
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": [_serialize_patient_row(patient) for patient in page],
            }
        )
