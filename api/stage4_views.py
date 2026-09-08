from datetime import timedelta

from django.conf import settings
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from patients.models import Case, Patient, Task, TaskStatus
from patients.timeline import FILTERS, timeline_page
from patients.views import _accessible_case_queryset, _accessible_task_queryset, can_access_case_data

from .cursors import CursorValidationError, decode_cursor, encode_cursor
from .permissions import HasMobileCaseAccess
from .stage4_serializers import (TimelinePageSerializer, UpcomingPageSerializer, UpcomingQuerySerializer, UpcomingSearchSerializer)
from .stage4_serializers import RelatedCasesPageSerializer
from .models import MobileDatasetState
from .throttles import DatabaseSearchThrottle
from .views import (_authorization_hash, _apply_case_search_body_filters, _normalize_patient_search_query,
                    _record_case_search_audit, _patient_search_class, _safe_search_length)


def cursor_context(user):
    dataset, _ = MobileDatasetState.objects.get_or_create(pk=1)
    return {"authorization": _authorization_hash(user), "dataset_epoch": str(dataset.epoch)}


def case_timeline_payload(case, user, *, filter_key, cursor=None):
    binding = {"case": case.pk, "filter": filter_key}
    context = cursor_context(user)
    state = decode_cursor(cursor, user=user, kind="case_timeline", binding=binding, context=context) if cursor else {}
    entries, position, snapshot = timeline_page(
        case, filter_key=filter_key, position=state.get("position"), snapshot=state.get("snapshot"),
    )
    next_cursor = encode_cursor(user=user, kind="case_timeline", binding=binding, context=context,
                                position=position, snapshot=snapshot) if position else None
    return {"results": entries, "next_cursor": next_cursor, "timezone": settings.TIME_ZONE}


class CaseTimelineView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasMobileCaseAccess]

    @extend_schema(parameters=[OpenApiParameter("filter", str, enum=list(dict(FILTERS))),
                               OpenApiParameter("cursor", str)], responses={200: TimelinePageSerializer})
    def get(self, request, pk):
        case = get_object_or_404(_accessible_case_queryset(request.user, include_archived=True), pk=pk)
        try:
            payload = case_timeline_payload(case, request.user, filter_key=request.GET.get("filter", "all"),
                                            cursor=request.GET.get("cursor"))
        except (CursorValidationError, ValueError, KeyError, TypeError):
            return Response({"detail": "Invalid or expired timeline cursor/filter. Refresh the timeline."}, status=400)
        return Response(TimelinePageSerializer(payload).data)


class UpcomingTasksView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasMobileCaseAccess]

    @extend_schema(parameters=[UpcomingQuerySerializer],
                   responses={200: UpcomingPageSerializer})
    def get(self, request):
        if "query" in request.GET or "q" in request.GET:
            return Response({"detail": "Use POST Upcoming search for patient queries."}, status=400)
        values = request.GET.dict()
        values["category"] = request.GET.getlist("category")
        values["subcategory"] = request.GET.getlist("subcategory")
        serializer = UpcomingQuerySerializer(data=values)
        serializer.is_valid(raise_exception=True)
        return self.page(request, serializer.validated_data)

    def page(self, request, values):
        today = timezone.localdate()
        try:
            start = values.get("start_date", today)
            end = start + timedelta(days=6)
        except (ValueError, OverflowError):
            return Response({"detail": "Invalid start_date."}, status=400)
        filters = {key: values.get(key) for key in ("assigned_to", "scope_context", "category", "subcategory")}
        normalized_query, normalized_phone = _normalize_patient_search_query(values.get("query", ""))
        binding = {"start": start.isoformat(), "filters": filters, "query": normalized_query, "phone": normalized_phone}
        context = cursor_context(request.user)
        queryset = _accessible_task_queryset(request.user, Task.objects.select_related("case__category", "assigned_user"))
        cases = _apply_case_search_body_filters(Case.objects.all(), request.user, filters, include_bucket=False)
        if normalized_query:
            if normalized_phone:
                cases = cases.filter(Q(phone_number=normalized_phone) | Q(alternate_phone_number=normalized_phone))
            else:
                match = Q(uhid__istartswith=normalized_query) | Q(first_name__istartswith=normalized_query) | Q(last_name__istartswith=normalized_query) | Q(patient_name__istartswith=normalized_query)
                if hasattr(Patient, "mtno"):
                    match |= Q(patient__mtno__istartswith=normalized_query)
                cases = cases.filter(match)
        queryset = queryset.filter(case_id__in=cases.values("pk"), status=TaskStatus.SCHEDULED, due_date__range=(start, end))
        try:
            state = decode_cursor(values["cursor"], user=request.user, kind="upcoming_tasks", binding=binding,
                                  context=context) if values.get("cursor") else {}
            snapshot = state.get("snapshot") or {"pk": queryset.aggregate(value=Max("pk"))["value"] or 0}
            queryset = queryset.filter(pk__lte=snapshot["pk"])
            if state.get("position"):
                pos = state["position"]
                queryset = queryset.filter(Q(due_date__gt=pos["date"]) |
                    Q(due_date=pos["date"], case_id__gt=pos["case"]) |
                    Q(due_date=pos["date"], case_id=pos["case"], pk__gt=pos["pk"]))
        except (CursorValidationError, ValueError, KeyError, TypeError):
            if normalized_query:
                _record_case_search_audit(request, search_class="invalid_cursor", normalized_length=len(normalized_query),
                                          result_count=0, denied=True)
            return Response({"detail": "Invalid or expired Upcoming cursor. Refresh Upcoming."}, status=400)
        tasks = list(queryset.order_by("due_date", "case_id", "pk")[:51])
        more, tasks = len(tasks) > 50, tasks[:50]
        next_cursor = None
        if more:
            last = tasks[-1]
            next_cursor = encode_cursor(user=request.user, kind="upcoming_tasks", binding=binding, context=context,
                position={"date": last.due_date.isoformat(), "case": last.case_id, "pk": last.pk}, snapshot=snapshot)
        payload = {"hospital_today": today, "start_date": start, "end_date": end, "timezone": settings.TIME_ZONE,
            "next_cursor": next_cursor, "results": [{
                "id": task.pk, "case_id": task.case_id, "patient_name": task.case.full_name or task.case.patient_name,
                "department": task.case.category.name, "title": task.title, "due_date": task.due_date,
                "assigned_user_id": task.assigned_user_id,
                "assigned_user_name": str(task.assigned_user) if task.assigned_user else "Unassigned",
            } for task in tasks]}
        if normalized_query:
            _record_case_search_audit(request, search_class=_patient_search_class(normalized_query, normalized_phone),
                                      normalized_length=len(normalized_query), result_count=len(tasks))
        return Response(UpcomingPageSerializer(payload).data)


class UpcomingSearchView(UpcomingTasksView):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["post", "options"]
    throttle_classes = [DatabaseSearchThrottle]
    database_throttle_scope = "api_case_search"
    search_audit_action = "case.search_attempt"
    search_object_type = "case_directory"

    @extend_schema(request=UpcomingSearchSerializer, responses={200: UpcomingPageSerializer})
    def post(self, request):
        if not can_access_case_data(request.user):
            _record_case_search_audit(request, search_class="permission_denied", normalized_length=_safe_search_length(request),
                                      result_count=0, denied=True)
            return Response({"detail": "Case search is not permitted."}, status=403)
        if request.query_params:
            _record_case_search_audit(request, search_class="url_parameters_rejected", normalized_length=0,
                                      result_count=0, denied=True)
            return Response({"detail": "Search parameters must be sent in the JSON body."}, status=400)
        serializer = UpcomingSearchSerializer(data=request.data)
        if not serializer.is_valid():
            _record_case_search_audit(request, search_class="invalid_search_request", normalized_length=_safe_search_length(request),
                                      result_count=0, denied=True)
            return Response({"detail": "Invalid search request.", "errors": serializer.errors}, status=400)
        return self.page(request, serializer.validated_data)


class RelatedCasesView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasMobileCaseAccess]

    @extend_schema(parameters=[OpenApiParameter("cursor", str)], responses={200: RelatedCasesPageSerializer})
    def get(self, request, pk):
        scoped = _accessible_case_queryset(request.user, Case.objects.select_related("category"), include_archived=True)
        selected = get_object_or_404(scoped, pk=pk)
        queryset = scoped.filter(patient_id=selected.patient_id) if selected.patient_id else scoped.filter(pk=pk)
        binding = {"case": pk, "patient": selected.patient_id}
        context = cursor_context(request.user)
        try:
            state = decode_cursor(request.GET["cursor"], user=request.user, kind="related_cases", binding=binding,
                                  context=context) if request.GET.get("cursor") else {}
            snapshot = state.get("snapshot") or {"pk": queryset.aggregate(value=Max("pk"))["value"] or 0}
            queryset = queryset.filter(pk__lte=snapshot["pk"])
            if state.get("position"):
                queryset = queryset.filter(pk__gt=state["position"]["pk"])
        except (CursorValidationError, ValueError, KeyError, TypeError):
            return Response({"detail": "Invalid or expired related cases cursor. Refresh cases."}, status=400)
        rows = list(queryset.order_by("pk")[:51])
        more, rows = len(rows) > 50, rows[:50]
        next_cursor = encode_cursor(user=request.user, kind="related_cases", binding=binding, context=context,
                                    position={"pk": rows[-1].pk}, snapshot=snapshot) if more else None
        return Response(RelatedCasesPageSerializer({"next_cursor": next_cursor, "results": [
            {"id": row.pk, "department": row.category.name, "diagnosis": row.diagnosis, "status": row.status}
            for row in rows
        ]}).data)
