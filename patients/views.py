from collections import OrderedDict
from pathlib import Path
from datetime import timedelta
from difflib import SequenceMatcher

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    ActivityLogForm,
    CallLogForm,
    CaseForm,
    DepartmentConfigForm,
    RoleSettingForm,
    TaskForm,
    UserRoleForm,
    VitalEntryForm,
)
from .models import (
    CallCommunicationStatus,
    CallLog,
    Case,
    CaseActivityLog,
    CaseStatus,
    DepartmentConfig,
    RCH_REMINDER_INTERVAL_DAYS,
    RCH_REMINDER_TASK_TITLE,
    RoleSetting,
    Task,
    TaskStatus,
    VitalEntry,
    build_default_tasks,
    cancel_open_rch_reminders,
    ensure_rch_reminder_task,
    ensure_default_role_settings,
    frequency_to_days,
    is_anc_case,
)

NON_SURGICAL_CASE_FILTER = (
    Q(category__name__iexact="Non Surgical")
    | Q(category__name__iexact="Non-Surgical")
    | Q(category__name__iexact="Nonsurgical")
)

CASE_CATEGORY_GROUP_FILTERS = {
    "anc": Q(category__name__iexact="ANC"),
    "surgery": Q(category__name__iexact="Surgery"),
    "non_surgical": NON_SURGICAL_CASE_FILTER,
}

CASE_DATA_CAPABILITIES = (
    "case_create",
    "case_edit",
    "task_create",
    "task_edit",
    "note_add",
    "manage_settings",
)



CHANGELOG_FILE = Path(settings.BASE_DIR) / "CHANGELOG.md"


def _load_changelog_entries():
    if not CHANGELOG_FILE.exists():
        return []

    entries = []
    current_entry = None

    for raw_line in CHANGELOG_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current_entry:
                entries.append(current_entry)
            current_entry = {"version": line[3:].strip(), "changes": []}
            continue

        if line.startswith("- ") and current_entry:
            current_entry["changes"].append(line[2:].strip())

    if current_entry:
        entries.append(current_entry)

    return entries

CAPABILITY_FIELD_MAP = {
    "case_create": "can_case_create",
    "case_edit": "can_case_edit",
    "task_create": "can_task_create",
    "task_edit": "can_task_edit",
    "note_add": "can_note_add",
    "manage_settings": "can_manage_settings",
}


def _user_role_settings_queryset(user):
    return RoleSetting.objects.filter(
        role_name__in=user.groups.values_list("name", flat=True),
    )


def has_capability(user, capability):
    if user.is_superuser:
        return True
    capability_field = CAPABILITY_FIELD_MAP.get(capability)
    if not capability_field:
        return False
    return _user_role_settings_queryset(user).filter(**{capability_field: True}).exists()


def is_doctor_admin(user):
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Doctor", "Admin"]).exists()


def can_access_case_data(user):
    if user.is_superuser:
        return True
    return _user_role_settings_queryset(user).filter(
        Q(can_case_create=True)
        | Q(can_case_edit=True)
        | Q(can_task_create=True)
        | Q(can_task_edit=True)
        | Q(can_note_add=True)
        | Q(can_manage_settings=True)
    ).exists()


def _metric_status(value, *, low_lt=None, high_gt=None, high_gte=None, neutral=False):
    if value is None:
        return "na"
    if neutral:
        return "neutral"
    if low_lt is not None and value < low_lt:
        return "low"
    if high_gte is not None and value >= high_gte:
        return "high"
    if high_gt is not None and value > high_gt:
        return "high"
    return "normal"


def _metric_percent(value, minimum, maximum):
    if value is None:
        return 0
    if maximum <= minimum:
        return 0
    raw = ((float(value) - minimum) / (maximum - minimum)) * 100
    return max(0, min(100, round(raw, 2)))


def _build_latest_vitals_summary(latest_vital):
    if not latest_vital:
        return []

    def format_integer(value):
        return str(int(value))

    def format_decimal_one(value):
        return f"{float(value):.1f}"

    metric_definitions = [
        {
            "key": "bp_systolic",
            "label": "BP Systolic",
            "unit": "mmHg",
            "value": latest_vital.bp_systolic,
            "minimum": 70,
            "maximum": 180,
            "low_lt": 90,
            "high_gte": 130,
            "formatter": format_integer,
        },
        {
            "key": "bp_diastolic",
            "label": "BP Diastolic",
            "unit": "mmHg",
            "value": latest_vital.bp_diastolic,
            "minimum": 40,
            "maximum": 120,
            "low_lt": 60,
            "high_gte": 80,
            "formatter": format_integer,
        },
        {
            "key": "pr",
            "label": "Pulse Rate",
            "unit": "bpm",
            "value": latest_vital.pr,
            "minimum": 40,
            "maximum": 140,
            "low_lt": 60,
            "high_gt": 100,
            "formatter": format_integer,
        },
        {
            "key": "spo2",
            "label": "SpO2",
            "unit": "%",
            "value": latest_vital.spo2,
            "minimum": 80,
            "maximum": 100,
            "low_lt": 95,
            "high_gt": 100,
            "formatter": format_integer,
        },
        {
            "key": "weight",
            "label": "Weight",
            "unit": "kg",
            "value": latest_vital.weight_kg,
            "minimum": 30,
            "maximum": 120,
            "neutral": True,
            "formatter": format_decimal_one,
        },
        {
            "key": "hemoglobin",
            "label": "Hemoglobin",
            "unit": "g/dL",
            "value": latest_vital.hemoglobin,
            "minimum": 4,
            "maximum": 16,
            "low_lt": 10,
            "high_gt": 13,
            "formatter": format_decimal_one,
        },
    ]

    summary = []
    for metric in metric_definitions:
        value = metric["value"]
        numeric_value = float(value) if value is not None else None
        status = _metric_status(
            numeric_value,
            low_lt=metric.get("low_lt"),
            high_gt=metric.get("high_gt"),
            high_gte=metric.get("high_gte"),
            neutral=metric.get("neutral", False),
        )
        if value is None:
            value_display = "N/A"
        else:
            formatted_value = metric["formatter"](value)
            value_display = f"{formatted_value} {metric['unit']}"
        summary.append(
            {
                "key": metric["key"],
                "label": metric["label"],
                "value": value,
                "value_display": value_display,
                "status": status,
                "percent": _metric_percent(numeric_value, metric["minimum"], metric["maximum"]),
            }
        )
    return summary


def _build_vitals_trend_payload(vitals_queryset):
    chart_rows = []
    for vital in vitals_queryset:
        chart_rows.append(
            {
                "label": timezone.localtime(vital.recorded_at).strftime("%d-%m-%y %H:%M"),
                "bp_systolic": vital.bp_systolic,
                "bp_diastolic": vital.bp_diastolic,
                "pr": vital.pr,
                "spo2": vital.spo2,
                "weight": float(vital.weight_kg) if vital.weight_kg is not None else None,
                "hemoglobin": float(vital.hemoglobin) if vital.hemoglobin is not None else None,
            }
        )
    if not chart_rows:
        return None
    return {
        "labels": [row["label"] for row in chart_rows],
        "datasets": {
            "bp_systolic": [row["bp_systolic"] for row in chart_rows],
            "bp_diastolic": [row["bp_diastolic"] for row in chart_rows],
            "pr": [row["pr"] for row in chart_rows],
            "spo2": [row["spo2"] for row in chart_rows],
            "hemoglobin": [row["hemoglobin"] for row in chart_rows],
            "weight": [row["weight"] for row in chart_rows],
        },
    }


class CaseDataAccessMixin:
    def dispatch(self, request, *args, **kwargs):
        if not can_access_case_data(request.user):
            return HttpResponseForbidden("You do not have permission to access case data.")
        return super().dispatch(request, *args, **kwargs)


class DashboardView(LoginRequiredMixin, CaseDataAccessMixin, ListView):
    model = Task
    template_name = "patients/dashboard.html"
    context_object_name = "today_tasks"
    task_only_fields = (
        "id",
        "title",
        "due_date",
        "status",
        "case_id",
        "case__id",
        "case__first_name",
        "case__last_name",
        "case__patient_name",
        "case__diagnosis",
        "case__phone_number",
        "case__referred_by",
        "case__high_risk",
        "case__ncd_flags",
        "case__category__name",
    )

    @staticmethod
    def _build_patient_day_cards(task_queryset, call_summary_by_case):
        grouped_tasks = OrderedDict()
        for task in task_queryset:
            key = (task.due_date, task.case_id)
            grouped_tasks.setdefault(key, []).append(task)

        cards = []
        for (_, _), grouped in grouped_tasks.items():
            first_task = grouped[0]
            case = first_task.case
            unique_titles = []
            seen_titles = set()
            for task in grouped:
                if task.title not in seen_titles:
                    unique_titles.append(task.title)
                    seen_titles.add(task.title)
            call_summary = call_summary_by_case.get(case.id, {})
            cards.append(
                {
                    "due_date": first_task.due_date,
                    "case_id": case.id,
                    "patient_name": case.full_name or case.patient_name,
                    "diagnosis": case.diagnosis or case.category.name,
                    "phone_number": case.phone_number,
                    "referred_by": case.referred_by,
                    "high_risk": case.high_risk,
                    "ncd_flags": case.ncd_flags or [],
                    "task_titles": unique_titles,
                    "call_status": call_summary.get("status", CallCommunicationStatus.NONE),
                    "failed_attempt_count": call_summary.get("failed_attempt_count", 0),
                    "latest_call_outcome": call_summary.get("latest_outcome", ""),
                }
            )
        return cards

    @staticmethod
    def _build_call_summaries(case_ids):
        if not case_ids:
            return {}
        summaries = {}
        grouped = OrderedDict()
        call_logs = (
            CallLog.objects.filter(case_id__in=case_ids)
            .only("id", "case_id", "task_id", "outcome", "created_at")
            .order_by("case_id", "-created_at", "-id")
        )
        for log in call_logs:
            grouped.setdefault(log.case_id, []).append(log)
        for case_id, logs in grouped.items():
            summaries[case_id] = CallLog.summarize_case(logs)
        return summaries

    def _task_queryset(self):
        return (
            Task.objects.select_related("case", "case__category")
            .only(*self.task_only_fields)
            .order_by("due_date", "case_id", "id")
        )

    def get_queryset(self):
        return Task.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        raw_upcoming_days = self.request.GET.get("upcoming_days", "7")
        try:
            upcoming_days = int(raw_upcoming_days)
        except (TypeError, ValueError):
            upcoming_days = 7
        upcoming_days = max(1, min(upcoming_days, 30))
        upper_bound = today + timedelta(days=upcoming_days)

        window_tasks = list(
            self._task_queryset()
            .exclude(status=TaskStatus.COMPLETED)
            .filter(due_date__lte=upper_bound)
        )

        today_tasks = []
        upcoming_tasks = []
        overdue_tasks = []
        for task in window_tasks:
            if task.due_date < today:
                overdue_tasks.append(task)
            if task.status == TaskStatus.SCHEDULED:
                if task.due_date == today:
                    today_tasks.append(task)
                elif task.due_date > today:
                    upcoming_tasks.append(task)

        awaiting_tasks = list(self._task_queryset().filter(status=TaskStatus.AWAITING_REPORTS))
        case_counts = Case.objects.aggregate(
            active_case_count=Count("id", filter=Q(status=CaseStatus.ACTIVE)),
            completed_case_count=Count("id", filter=Q(status=CaseStatus.COMPLETED)),
            anc_case_count=Count("id", filter=Q(status=CaseStatus.ACTIVE) & CASE_CATEGORY_GROUP_FILTERS["anc"]),
            surgery_case_count=Count(
                "id",
                filter=Q(status=CaseStatus.ACTIVE) & CASE_CATEGORY_GROUP_FILTERS["surgery"],
            ),
            non_surgical_case_count=Count(
                "id",
                filter=Q(status=CaseStatus.ACTIVE) & CASE_CATEGORY_GROUP_FILTERS["non_surgical"],
            ),
        )

        context["today_tasks"] = today_tasks
        context["upcoming_tasks"] = upcoming_tasks
        context["overdue_tasks"] = overdue_tasks
        context["awaiting_tasks"] = awaiting_tasks
        case_ids = sorted({task.case_id for task in [*today_tasks, *upcoming_tasks, *overdue_tasks]})
        call_summary_by_case = self._build_call_summaries(case_ids)

        context["today_cards"] = self._build_patient_day_cards(today_tasks, call_summary_by_case)
        context["upcoming_cards"] = self._build_patient_day_cards(upcoming_tasks, call_summary_by_case)
        context["overdue_cards"] = self._build_patient_day_cards(overdue_tasks, call_summary_by_case)
        context["call_log_form"] = CallLogForm()
        context["anc_case_count"] = case_counts["anc_case_count"]
        context["surgery_case_count"] = case_counts["surgery_case_count"]
        context["non_surgical_case_count"] = case_counts["non_surgical_case_count"]
        context["active_case_count"] = case_counts["active_case_count"]
        context["completed_case_count"] = case_counts["completed_case_count"]
        context["upcoming_days"] = upcoming_days
        return context


class CaseListView(LoginRequiredMixin, CaseDataAccessMixin, ListView):
    model = Case
    template_name = "patients/case_list.html"
    context_object_name = "cases"
    paginate_by = 25

    def get_queryset(self):
        task_count_subquery = (
            Task.objects.filter(case_id=OuterRef("pk"))
            .order_by()
            .values("case_id")
            .annotate(total=Count("id"))
            .values("total")[:1]
        )
        queryset = (
            Case.objects.select_related("category")
            .only(
                "id",
                "uhid",
                "first_name",
                "last_name",
                "patient_name",
                "gender",
                "date_of_birth",
                "place",
                "phone_number",
                "status",
                "updated_at",
                "category__id",
                "category__name",
            )
            .annotate(task_count=Coalesce(Subquery(task_count_subquery, output_field=IntegerField()), 0))
        )
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        category = self.request.GET.get("category", "").strip()
        category_group = self.request.GET.get("category_group", "").strip()
        assigned_user = self.request.GET.get("assigned_user", "").strip()
        due_start = self.request.GET.get("due_start", "").strip()
        due_end = self.request.GET.get("due_end", "").strip()

        if q:
            queryset = queryset.filter(
                Q(uhid__icontains=q)
                | Q(phone_number__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(patient_name__icontains=q)
                | Q(place__icontains=q)
            )
        if status:
            queryset = queryset.filter(status=status)
        if category_group in CASE_CATEGORY_GROUP_FILTERS:
            queryset = queryset.filter(CASE_CATEGORY_GROUP_FILTERS[category_group])
        if category:
            queryset = queryset.filter(category_id=category)
        if assigned_user:
            queryset = queryset.filter(
                Exists(Task.objects.filter(case_id=OuterRef("pk"), assigned_user_id=assigned_user))
            )
        if due_start:
            queryset = queryset.filter(
                Exists(Task.objects.filter(case_id=OuterRef("pk"), due_date__gte=due_start))
            )
        if due_end:
            queryset = queryset.filter(
                Exists(Task.objects.filter(case_id=OuterRef("pk"), due_date__lte=due_end))
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {
            k: self.request.GET.get(k, "")
            for k in ["q", "status", "category", "category_group", "assigned_user", "due_start", "due_end"]
        }
        context["case_statuses"] = CaseStatus.choices
        context["categories"] = DepartmentConfig.objects.only("id", "name")
        context["users"] = get_user_model().objects.only("id", "username").order_by("username")
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["filter_querystring"] = query_params.urlencode()
        return context


class CaseAutocompleteView(LoginRequiredMixin, CaseDataAccessMixin, View):
    allowed_fields = {"place", "diagnosis", "referred_by"}
    min_query_length = 2
    max_results = 8
    scan_multiplier = 8

    @staticmethod
    def _normalize_value(value):
        return " ".join((value or "").split())

    @staticmethod
    def _display_value(value):
        if value.isupper() and len(value) <= 5:
            return value
        return value.title()

    def get(self, request):
        field = (request.GET.get("field") or "").strip()
        if field not in self.allowed_fields:
            return JsonResponse({"error": "Invalid field."}, status=400)

        normalized_query = self._normalize_value(request.GET.get("q")).lower()
        if len(normalized_query) < self.min_query_length:
            return JsonResponse([], safe=False)

        grouped = {}

        queryset = (
            Case.objects.exclude(**{f"{field}__isnull": True})
            .exclude(**{field: ""})
            .filter(**{f"{field}__istartswith": normalized_query.split(" ", 1)[0]})
            .values_list(field, flat=True)
            .order_by(field)
        )

        scan_limit = self.max_results * self.scan_multiplier
        for raw_value in queryset[:scan_limit]:
            suggestion = self._normalize_value(raw_value)
            if not suggestion:
                continue
            normalized_suggestion = suggestion.lower()
            if not normalized_suggestion.startswith(normalized_query):
                continue

            grouped[normalized_suggestion] = self._display_value(suggestion)
            if len(grouped) >= self.max_results:
                break

        payload = [grouped[key] for key in sorted(grouped.keys())[: self.max_results]]
        return JsonResponse(payload, safe=False)


class UniversalCaseSearchView(LoginRequiredMixin, CaseDataAccessMixin, View):
    min_query_length = 2
    max_results = 10
    category_filters = {
        "anc": Q(category__name__iexact="ANC"),
        "surgical": Q(category__name__iexact="Surgery"),
        "non_surgical": (
            Q(category__name__iexact="Non Surgical")
            | Q(category__name__iexact="Non-Surgical")
            | Q(category__name__iexact="Nonsurgical")
        ),
    }

    @staticmethod
    def _normalized(value):
        return " ".join((value or "").split())

    @staticmethod
    def _score_value(query, value):
        normalized_value = UniversalCaseSearchView._normalized(value).lower()
        if not normalized_value:
            return 0
        if normalized_value == query:
            return 130
        if normalized_value.startswith(query):
            return 110
        if query in normalized_value:
            return 90
        if any(part.startswith(query) for part in normalized_value.split()):
            return 75
        ratio = SequenceMatcher(None, query, normalized_value).ratio()
        if ratio >= 0.65:
            return int(ratio * 60)
        return 0

    def _category_query(self, raw_categories):
        clauses = [self.category_filters.get(raw) for raw in raw_categories if raw in self.category_filters]
        if not clauses:
            return Q()
        category_query = clauses[0]
        for clause in clauses[1:]:
            category_query |= clause
        return category_query

    def get(self, request):
        raw_query = self._normalized(request.GET.get("q"))
        query = raw_query.lower()
        if len(query) < self.min_query_length:
            return JsonResponse({"results": []})

        selected_categories = request.GET.getlist("category")
        category_query = self._category_query(selected_categories)
        base_query = (
            Q(uhid__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(patient_name__icontains=query)
            | Q(phone_number__icontains=query)
            | Q(diagnosis__icontains=query)
        )

        cases = list(
            Case.objects.select_related("category")
            .filter(base_query)
            .filter(category_query)
            .only(
                "id",
                "uhid",
                "first_name",
                "last_name",
                "patient_name",
                "age",
                "place",
                "diagnosis",
                "phone_number",
                "high_risk",
                "referred_by",
                "ncd_flags",
                "updated_at",
                "category__name",
            )[:150]
        )

        scored = []
        for case in cases:
            full_name = case.full_name or case.patient_name
            top_score = max(
                self._score_value(query, case.uhid),
                self._score_value(query, full_name),
                self._score_value(query, case.phone_number),
                self._score_value(query, case.diagnosis),
            )
            if top_score <= 0:
                continue
            scored.append((top_score, case.updated_at, case))

        scored.sort(key=lambda row: (-row[0], -row[1].timestamp(), row[2].uhid))
        top_cases = [row[2] for row in scored[: self.max_results]]

        results = []
        for case in top_cases:
            diagnosis = self._normalized(case.diagnosis) or "—"
            village = self._normalized(case.place) or "—"
            age = case.age if case.age is not None else "—"
            category = case.category.name
            tags = [
                {"kind": "category", "label": category},
            ]
            if case.high_risk:
                tags.append({"kind": "high_risk", "label": "High-risk", "icon": "❗"})
            if case.referred_by:
                tags.append({"kind": "referred", "label": "Referred", "icon": "⭐"})
            if case.ncd_flags:
                tags.append({"kind": "ncd", "label": "NCD", "icon": "🏷️"})

            results.append(
                {
                    "id": case.id,
                    "uhid": case.uhid,
                    "name": case.full_name or case.patient_name,
                    "age": age,
                    "village": village,
                    "diagnosis": diagnosis,
                    "phone_number": case.phone_number,
                    "tags": tags,
                    "detail_url": reverse("patients:case_detail", kwargs={"pk": case.pk}),
                }
            )
        return JsonResponse({"results": results})


class CaseCreateView(LoginRequiredMixin, CreateView):
    model = Case
    form_class = CaseForm
    template_name = "patients/case_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_capability(request.user, "case_create"):
            return HttpResponseForbidden("You do not have permission to create cases.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        if self.object.review_frequency and not self.object.review_date:
            self.object.review_date = timezone.localdate() + timedelta(days=frequency_to_days(self.object.review_frequency))
            self.object.save(update_fields=["review_date", "updated_at", "patient_name"])
        created_tasks = build_default_tasks(self.object, self.request.user)
        CaseActivityLog.objects.create(case=self.object, user=self.request.user, note=f"Case created with {len(created_tasks)} starter task(s)")
        reminder = ensure_rch_reminder_task(self.object, self.request.user)
        if reminder:
            CaseActivityLog.objects.create(
                case=self.object,
                task=reminder,
                user=self.request.user,
                note=f"RCH reminder scheduled for {reminder.due_date:%d-%m-%Y}.",
            )
        return response

    def get_success_url(self):
        return reverse("patients:case_detail", kwargs={"pk": self.object.pk})


class CaseDetailView(LoginRequiredMixin, DetailView):
    model = Case
    template_name = "patients/case_detail.html"
    context_object_name = "case"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        case = self.object
        context["tasks"] = case.tasks.select_related("assigned_user")
        latest_vital = case.vitals.order_by("-recorded_at", "-id").first()
        context["today"] = timezone.localdate()
        context["activity_logs"] = case.activity_logs.select_related("user", "task")[:50]
        context["call_logs"] = case.call_logs.select_related("staff_user", "task")[:50]
        context["has_vitals"] = latest_vital is not None
        context["latest_vitals_recorded_at"] = timezone.localtime(latest_vital.recorded_at) if latest_vital else None
        context["vitals_summary_metrics"] = _build_latest_vitals_summary(latest_vital)
        context["vitals_detail_url"] = reverse("patients:case_vitals", kwargs={"pk": case.pk})
        context["task_form"] = TaskForm()
        context["log_form"] = ActivityLogForm()
        call_log_form = CallLogForm()
        call_log_form.fields["task"].queryset = case.tasks.order_by("due_date", "id")
        call_log_form.fields["task"].required = False
        context["call_log_form"] = call_log_form
        context["can_task_create"] = has_capability(self.request.user, "task_create")
        context["can_task_edit"] = has_capability(self.request.user, "task_edit")
        context["can_note_add"] = has_capability(self.request.user, "note_add")
        context["can_vitals_edit"] = has_capability(self.request.user, "task_edit")
        return context

    def dispatch(self, request, *args, **kwargs):
        if not can_access_case_data(request.user):
            return HttpResponseForbidden("You do not have permission to view case details.")
        return super().dispatch(request, *args, **kwargs)


class CaseVitalsDetailView(LoginRequiredMixin, DetailView):
    model = Case
    template_name = "patients/vitals_detail.html"
    context_object_name = "case"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        case = self.object
        vitals = list(case.vitals.select_related("created_by", "updated_by").order_by("-recorded_at", "-id"))
        context["vitals"] = vitals
        context["vitals_trend_payload"] = _build_vitals_trend_payload(reversed(vitals))
        context["can_vitals_edit"] = has_capability(self.request.user, "task_edit")
        latest_vital = vitals[0] if vitals else None
        context["latest_vitals_summary"] = _build_latest_vitals_summary(latest_vital)
        context["latest_vitals_recorded_at"] = timezone.localtime(latest_vital.recorded_at) if latest_vital else None
        return context

    def dispatch(self, request, *args, **kwargs):
        if not can_access_case_data(request.user):
            return HttpResponseForbidden("You do not have permission to view case vitals.")
        return super().dispatch(request, *args, **kwargs)


class CaseUpdateView(LoginRequiredMixin, UpdateView):
    model = Case
    form_class = CaseForm
    template_name = "patients/case_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_capability(request.user, "case_edit"):
            return HttpResponseForbidden("You do not have permission to edit cases.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        case = self.get_object()
        old_status = case.status
        had_rch_number = bool(case.rch_number)
        new_status = form.cleaned_data["status"]
        grey_list_cutoff = timezone.localdate() - timedelta(days=30)
        has_grey_tasks = case.tasks.exclude(status=TaskStatus.COMPLETED).filter(due_date__lt=grey_list_cutoff).exists()
        if has_grey_tasks and new_status in [CaseStatus.LOSS_TO_FOLLOW_UP, CaseStatus.ACTIVE] and not is_doctor_admin(self.request.user):
            form.add_error("status", "Only Doctor/Admin can set Grey List cases to Active or Loss to Follow-up.")
            return self.form_invalid(form)
        if old_status != new_status:
            CaseActivityLog.objects.create(case=case, user=self.request.user, note=f"Case status changed: {old_status} → {new_status}")
        response = super().form_valid(form)
        if not is_anc_case(self.object):
            cancelled_count = cancel_open_rch_reminders(self.object)
            if cancelled_count:
                CaseActivityLog.objects.create(
                    case=self.object,
                    user=self.request.user,
                    note=f"Cancelled {cancelled_count} open RCH reminder task(s) because category is no longer ANC.",
                )
            return response

        if self.object.rch_number:
            cancelled_count = cancel_open_rch_reminders(self.object)
            if cancelled_count:
                CaseActivityLog.objects.create(
                    case=self.object,
                    user=self.request.user,
                    note=f"RCH number captured. Cancelled {cancelled_count} open RCH reminder task(s).",
                )
        else:
            reminder = ensure_rch_reminder_task(self.object, self.request.user)
            if reminder:
                CaseActivityLog.objects.create(
                    case=self.object,
                    task=reminder,
                    user=self.request.user,
                    note=f"RCH reminder scheduled for {reminder.due_date:%d-%m-%Y}.",
                )
        if had_rch_number and not self.object.rch_number:
            reminder = ensure_rch_reminder_task(self.object, self.request.user)
            if reminder:
                CaseActivityLog.objects.create(
                    case=self.object,
                    task=reminder,
                    user=self.request.user,
                    note=f"RCH removed. Reminder scheduled for {reminder.due_date:%d-%m-%Y}.",
                )
        return response

    def get_success_url(self):
        return reverse("patients:case_detail", kwargs={"pk": self.object.pk})


class TaskCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not has_capability(request.user, "task_create"):
            return HttpResponseForbidden("You do not have permission to create tasks.")
        case = get_object_or_404(Case, pk=pk)
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.case = case
            task.created_by = request.user
            try:
                task.full_clean()
                task.save()
            except ValidationError:
                messages.error(request, "Could not add task. Please check the inputs.")
            else:
                CaseActivityLog.objects.create(case=case, task=task, user=request.user, note=f"Task created: {task.title}")
                messages.success(request, "Task added.")
        else:
            messages.error(request, "Could not add task. Please check the inputs.")
        return redirect("patients:case_detail", pk=pk)


class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "patients/task_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_capability(request.user, "task_edit"):
            return HttpResponseForbidden("You do not have permission to edit tasks.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        previous_task = self.get_object()
        previous_status = previous_task.status
        response = super().form_valid(form)
        CaseActivityLog.objects.create(case=self.object.case, task=self.object, user=self.request.user, note=f"Task updated: {self.object.title} ({self.object.status})")
        if (
            previous_status != TaskStatus.COMPLETED
            and self.object.status == TaskStatus.COMPLETED
            and self.object.title == RCH_REMINDER_TASK_TITLE
        ):
            completed_local = timezone.localtime(self.object.completed_at) if self.object.completed_at else timezone.now()
            next_due_date = completed_local.date() + timedelta(days=RCH_REMINDER_INTERVAL_DAYS)
            reminder = ensure_rch_reminder_task(self.object.case, self.request.user, due_date=next_due_date)
            if reminder:
                CaseActivityLog.objects.create(
                    case=self.object.case,
                    task=reminder,
                    user=self.request.user,
                    note=f"RCH still pending. Next reminder scheduled for {reminder.due_date:%d-%m-%Y}.",
                )
        return response

    def get_success_url(self):
        return reverse("patients:case_detail", kwargs={"pk": self.object.case_id})


class AddCaseNoteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not has_capability(request.user, "note_add"):
            return HttpResponseForbidden("You do not have permission to add notes.")
        case = get_object_or_404(Case, pk=pk)
        form = ActivityLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.case = case
            log.user = request.user
            log.save()
            messages.success(request, "Note added.")
        else:
            messages.error(request, "Could not save note.")
        return redirect("patients:case_detail", pk=pk)


class AddCallLogView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not has_capability(request.user, "note_add"):
            return HttpResponseForbidden("You do not have permission to add call logs.")
        case = get_object_or_404(Case, pk=pk)
        form = CallLogForm(request.POST)
        form.fields["task"].queryset = case.tasks.all()
        if form.is_valid():
            log = form.save(commit=False)
            log.case = case
            log.staff_user = request.user
            log.save()
            CaseActivityLog.objects.create(
                case=case,
                task=log.task,
                user=request.user,
                note=f"Call outcome logged: {log.get_outcome_display()}",
            )
            messages.success(request, "Call outcome logged.")
        else:
            messages.error(request, "Could not log call outcome.")
        return redirect("patients:case_detail", pk=pk)


class VitalEntryCreateView(LoginRequiredMixin, View):
    template_name = "patients/vitals_form.html"

    def _check_access(self, request):
        if not can_access_case_data(request.user):
            return HttpResponseForbidden("You do not have permission to access case data.")
        if not has_capability(request.user, "task_edit"):
            return HttpResponseForbidden("You do not have permission to add vitals.")
        return None

    def get(self, request, pk):
        denied = self._check_access(request)
        if denied:
            return denied
        case = get_object_or_404(Case, pk=pk)
        form = VitalEntryForm()
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "case": case,
                "is_edit": False,
                "show_hb_warning": form.hb_warning,
            },
        )

    def post(self, request, pk):
        denied = self._check_access(request)
        if denied:
            return denied
        case = get_object_or_404(Case, pk=pk)
        form = VitalEntryForm(request.POST)
        if form.is_valid():
            vital = form.save(commit=False)
            vital.case = case
            vital.created_by = request.user
            vital.updated_by = request.user
            vital.save()
            CaseActivityLog.objects.create(case=case, user=request.user, note="Vitals entry recorded.")
            if form.hb_warning:
                form = VitalEntryForm(instance=vital)
                form.hb_warning = True
                return render(
                    request,
                    self.template_name,
                    {
                        "form": form,
                        "case": case,
                        "is_edit": True,
                        "vital": vital,
                        "saved_successfully": True,
                        "show_hb_warning": True,
                    },
                )
            messages.success(request, "Vitals recorded.")
            return redirect("patients:case_detail", pk=case.pk)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "case": case,
                "is_edit": False,
                "show_hb_warning": form.hb_warning,
            },
        )


class VitalEntryUpdateView(LoginRequiredMixin, View):
    template_name = "patients/vitals_form.html"

    def _check_access(self, request):
        if not can_access_case_data(request.user):
            return HttpResponseForbidden("You do not have permission to access case data.")
        if not has_capability(request.user, "task_edit"):
            return HttpResponseForbidden("You do not have permission to edit vitals.")
        return None

    def get(self, request, pk):
        denied = self._check_access(request)
        if denied:
            return denied
        vital = get_object_or_404(VitalEntry.objects.select_related("case"), pk=pk)
        form = VitalEntryForm(instance=vital)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "vital": vital,
                "case": vital.case,
                "is_edit": True,
                "show_hb_warning": form.hb_warning,
            },
        )

    def post(self, request, pk):
        denied = self._check_access(request)
        if denied:
            return denied
        vital = get_object_or_404(VitalEntry.objects.select_related("case"), pk=pk)
        form = VitalEntryForm(request.POST, instance=vital)
        if form.is_valid():
            updated_vital = form.save(commit=False)
            updated_vital.updated_by = request.user
            if updated_vital.created_by_id is None:
                updated_vital.created_by = request.user
            updated_vital.save()
            CaseActivityLog.objects.create(case=updated_vital.case, user=request.user, note="Vitals entry updated.")
            if form.hb_warning:
                form = VitalEntryForm(instance=updated_vital)
                form.hb_warning = True
                return render(
                    request,
                    self.template_name,
                    {
                        "form": form,
                        "vital": updated_vital,
                        "case": updated_vital.case,
                        "is_edit": True,
                        "saved_successfully": True,
                        "show_hb_warning": True,
                    },
                )
            messages.success(request, "Vitals updated.")
            return redirect("patients:case_detail", pk=updated_vital.case.pk)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "vital": vital,
                "case": vital.case,
                "is_edit": True,
                "show_hb_warning": form.hb_warning,
            },
        )


class ChangelogView(LoginRequiredMixin, View):
    template_name = "patients/changelog.html"

    def get(self, request):
        if not has_capability(request.user, "manage_settings"):
            return HttpResponseForbidden("Only admins can access changelog.")

        context = {"changelog_entries": _load_changelog_entries()}
        return render(request, self.template_name, context)


class AdminSettingsView(LoginRequiredMixin, View):
    template_name = "patients/settings.html"

    def _check_access(self, request):
        if not has_capability(request.user, "manage_settings"):
            return HttpResponseForbidden("Only admins can access settings.")
        return None

    def get(self, request):
        denied = self._check_access(request)
        if denied:
            return denied
        ensure_default_role_settings()
        context = {
            "role_form": RoleSettingForm(),
            "department_form": DepartmentConfigForm(),
            "user_role_form": UserRoleForm(),
            "roles": RoleSetting.objects.all(),
            "departments": DepartmentConfig.objects.all(),
            "groups": Group.objects.order_by("name"),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        denied = self._check_access(request)
        if denied:
            return denied

        action = request.POST.get("action")
        if action == "create_role":
            form = RoleSettingForm(request.POST)
            if form.is_valid():
                role = form.save()
                Group.objects.get_or_create(name=role.role_name)
                messages.success(request, "Role setting saved.")
            else:
                messages.error(request, f"Role form errors: {form.errors}")

        elif action == "create_department":
            form = DepartmentConfigForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Category saved.")
            else:
                messages.error(request, f"Category form errors: {form.errors}")

        elif action == "assign_role":
            form = UserRoleForm(request.POST)
            if form.is_valid():
                user = form.cleaned_data["user"]
                role = form.cleaned_data["role"]
                user.groups.clear()
                user.groups.add(role)
                messages.success(request, f"Assigned role {role.name} to {user.username}.")
            else:
                messages.error(request, f"User role form errors: {form.errors}")

        return redirect("patients:settings")
