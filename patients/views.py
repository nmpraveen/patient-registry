import hashlib
import json
import secrets
from base64 import urlsafe_b64encode
from collections import OrderedDict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.db.models import Count, Exists, IntegerField, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.crypto import constant_time_compare
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    ActivityLogForm,
    CallLogForm,
    CaseForm,
    DepartmentThemeFormSet,
    DepartmentConfigForm,
    DeviceApprovalPolicyForm,
    RecentCaseUpdateForm,
    RoleSettingForm,
    SeedMockDataForm,
    TaskForm,
    ThemeSettingsForm,
    UserRoleForm,
    VitalEntryForm,
)
from .models import (
    ActivityEventType,
    CallCommunicationStatus,
    CallLog,
    Case,
    CaseActivityLog,
    CaseStatus,
    DepartmentConfig,
    DeviceApprovalPolicy,
    DEVICE_APPROVAL_MAX_APPROVED,
    Gender,
    RCH_REMINDER_INTERVAL_DAYS,
    RCH_REMINDER_TASK_TITLE,
    RoleSetting,
    STAFF_PILOT_ROLE_NAME,
    STAFF_ROLE_NAME,
    StaffDeviceCredential,
    StaffDeviceCredentialStatus,
    Task,
    TaskStatus,
    ThemeSettings,
    VitalEntry,
    build_default_tasks,
    cancel_open_rch_reminders,
    clone_role_setting,
    ensure_rch_reminder_task,
    ensure_default_role_settings,
    frequency_to_days,
    is_anc_case,
)
from .theme import build_theme_category_colors, get_default_category_theme, mix_colors, resolve_category_theme

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
TIMELINE_FILTER_OPTIONS = (
    ("all", "All"),
    ("calls", "Calls"),
    ("tasks", "Tasks"),
    ("notes", "Notes"),
)
TASK_NOTE_MARKER = "[Task:"
LEGACY_TASK_NOTE_PREFIX = "Task note updated:"
RECENT_CASE_LIMIT_DEFAULT = 10
RECENT_CASE_LIMIT_MAX = 10
RECENT_CASE_VIEW_ROLES = ("Doctor", "Admin", "Reception")
RECENT_CASE_EDIT_ROLES = ("Doctor", "Admin")
PENDING_DEVICE_LOGIN_SESSION_KEY = "device_access_pending_login"
DEVICE_REGISTRATION_STATE_SESSION_KEY = "device_access_registration_state"
DEVICE_AUTHENTICATION_STATE_SESSION_KEY = "device_access_authentication_state"


def _bytes_to_base64url(value):
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _load_webauthn_dependencies():
    from webauthn import (
        generate_authentication_options,
        generate_registration_options,
        options_to_json,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticationCredential,
        PublicKeyCredentialDescriptor,
        PublicKeyCredentialType,
        RegistrationCredential,
        UserVerificationRequirement,
    )

    return {
        "AuthenticationCredential": AuthenticationCredential,
        "PublicKeyCredentialDescriptor": PublicKeyCredentialDescriptor,
        "PublicKeyCredentialType": PublicKeyCredentialType,
        "RegistrationCredential": RegistrationCredential,
        "UserVerificationRequirement": UserVerificationRequirement,
        "base64url_to_bytes": base64url_to_bytes,
        "generate_authentication_options": generate_authentication_options,
        "generate_registration_options": generate_registration_options,
        "options_to_json": options_to_json,
        "verify_authentication_response": verify_authentication_response,
        "verify_registration_response": verify_registration_response,
    }


def _safe_redirect_target(request, value):
    fallback = reverse_lazy(settings.LOGIN_REDIRECT_URL)
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return str(fallback)


def _pending_device_login_state(request):
    state = request.session.get(PENDING_DEVICE_LOGIN_SESSION_KEY)
    if not isinstance(state, dict):
        return None
    return state


def _set_pending_device_login(request, *, user, backend, redirect_to):
    request.session[PENDING_DEVICE_LOGIN_SESSION_KEY] = {
        "user_id": user.pk,
        "backend": backend or settings.AUTHENTICATION_BACKENDS[0],
        "redirect_to": _safe_redirect_target(request, redirect_to),
    }


def _clear_pending_device_login(request):
    request.session.pop(PENDING_DEVICE_LOGIN_SESSION_KEY, None)
    request.session.pop(DEVICE_REGISTRATION_STATE_SESSION_KEY, None)
    request.session.pop(DEVICE_AUTHENTICATION_STATE_SESSION_KEY, None)


def _pending_device_login_user(request):
    state = _pending_device_login_state(request)
    if not state:
        return None
    User = get_user_model()
    return User.objects.filter(pk=state.get("user_id")).first()


def _device_policy():
    return DeviceApprovalPolicy.get_solo()


def _is_device_approval_target_user(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return _device_policy().targets_user(user)


def _approved_device_queryset(user):
    return StaffDeviceCredential.objects.filter(user=user, status=StaffDeviceCredentialStatus.APPROVED)


def _approved_device_count(user):
    return _approved_device_queryset(user).count()


def _can_register_device(user):
    return _approved_device_count(user) < DEVICE_APPROVAL_MAX_APPROVED


def _trusted_device_cookie_name():
    return settings.DEVICE_APPROVAL_TRUST_COOKIE_NAME


def _trusted_device_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _default_origin_for_request(request):
    scheme = "https" if request.is_secure() or settings.SESSION_COOKIE_SECURE else "http"
    return f"{scheme}://{request.get_host()}"


def _expected_webauthn_origin(request):
    origin = _default_origin_for_request(request)
    allowed_origins = getattr(settings, "WEBAUTHN_ALLOWED_ORIGINS", [])
    if allowed_origins and origin not in allowed_origins:
        return allowed_origins[0]
    return origin


def _expected_webauthn_rp_id(request):
    configured_rp_id = getattr(settings, "WEBAUTHN_RP_ID", "").strip()
    if configured_rp_id:
        return configured_rp_id
    return request.get_host().split(":", 1)[0]


def _set_trusted_device_cookie(response, credential):
    token = secrets.token_urlsafe(32)
    credential.trusted_token_hash = _trusted_device_token_hash(token)
    credential.trusted_token_created_at = timezone.now()
    credential.save(update_fields=["trusted_token_hash", "trusted_token_created_at"])
    response.set_cookie(
        _trusted_device_cookie_name(),
        f"{credential.pk}:{token}",
        max_age=settings.DEVICE_APPROVAL_TRUST_COOKIE_AGE,
        httponly=True,
        samesite="Lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )


def _get_trusted_device_credential(request, user):
    raw_cookie = request.COOKIES.get(_trusted_device_cookie_name(), "")
    if ":" not in raw_cookie:
        return None

    credential_pk, token = raw_cookie.split(":", 1)
    if not credential_pk.isdigit() or not token:
        return None

    credential = StaffDeviceCredential.objects.filter(
        pk=int(credential_pk),
        user=user,
        status=StaffDeviceCredentialStatus.APPROVED,
    ).first()
    if not credential or not credential.trusted_token_hash:
        return None
    if not constant_time_compare(credential.trusted_token_hash, _trusted_device_token_hash(token)):
        return None
    return credential


def _credential_descriptor_from_record(credential, deps):
    return deps["PublicKeyCredentialDescriptor"](
        id=deps["base64url_to_bytes"](credential.credential_id),
        type=deps["PublicKeyCredentialType"].PUBLIC_KEY,
    )


def _pending_device_json_error(message, status=400):
    return JsonResponse({"message": message}, status=status)


def _parse_request_json(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


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


def _user_role_settings(user):
    if user.is_superuser:
        return []
    cached_settings = getattr(user, "_cached_role_settings", None)
    if cached_settings is None:
        cached_settings = list(
            _user_role_settings_queryset(user).only(
                "role_name",
                "can_case_create",
                "can_case_edit",
                "can_task_create",
                "can_task_edit",
                "can_note_add",
                "can_manage_settings",
            )
        )
        user._cached_role_settings = cached_settings
    return cached_settings


def has_capability(user, capability):
    if user.is_superuser:
        return True
    capability_field = CAPABILITY_FIELD_MAP.get(capability)
    if not capability_field:
        return False
    capability_cache = getattr(user, "_capability_cache", None)
    if capability_cache is None:
        capability_cache = {}
        user._capability_cache = capability_cache
    if capability in capability_cache:
        return capability_cache[capability]
    allowed = any(getattr(role_setting, capability_field) for role_setting in _user_role_settings(user))
    capability_cache[capability] = allowed
    return allowed


def is_doctor_admin(user):
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Doctor", "Admin"]).exists()


def delete_seeded_mock_data():
    seeded_cases = Case.objects.filter(metadata__source="seed_mock_data")
    CallLog.objects.filter(case__in=seeded_cases).delete()
    CaseActivityLog.objects.filter(case__in=seeded_cases).delete()
    deleted_count, _ = seeded_cases.delete()
    return deleted_count


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


def create_case_activity(*, case, note, user=None, task=None, event_type=ActivityEventType.SYSTEM):
    return CaseActivityLog.objects.create(
        case=case,
        task=task,
        user=user,
        event_type=event_type,
        note=note,
    )


def _request_wants_json(request):
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    return "application/json" in request.headers.get("Accept", "")


def _forbidden_response(request, message):
    if _request_wants_json(request):
        return JsonResponse({"message": message}, status=403)
    return HttpResponseForbidden(message)


def _clamp_recent_case_limit(raw_limit):
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = RECENT_CASE_LIMIT_DEFAULT
    return max(1, min(limit, RECENT_CASE_LIMIT_MAX))


def _truncate_text(value, max_length=42):
    text = (value or "").strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _can_view_recent_cases(user):
    if user.is_superuser:
        return True
    group_names = _user_group_names(user)
    if group_names & set(RECENT_CASE_VIEW_ROLES):
        return True
    return has_capability(user, "case_edit") and has_capability(user, "task_edit")


def _can_edit_recent_cases(user):
    if user.is_superuser:
        return True
    group_names = _user_group_names(user)
    if group_names and group_names.issubset({"Reception"}):
        return False
    return has_capability(user, "case_edit") and has_capability(user, "task_edit")


def _user_group_names(user):
    if user.is_superuser:
        return set()
    cached_names = getattr(user, "_cached_group_names", None)
    if cached_names is None:
        cached_names = {role_setting.role_name for role_setting in _user_role_settings(user)}
        user._cached_group_names = cached_names
    return cached_names


def _recent_case_task_queryset():
    return Task.objects.only("id", "case_id", "title", "due_date", "status", "notes").order_by("due_date", "id")


def _recent_case_queryset(limit=None, *, include_tasks=True):
    queryset = (
        Case.objects.select_related("category")
        .only(
            "id",
            "first_name",
            "last_name",
            "patient_name",
            "age",
            "date_of_birth",
            "gender",
            "diagnosis",
            "notes",
            "created_at",
            "category__id",
            "category__name",
        )
        .order_by("-created_at", "-id")
    )
    if include_tasks:
        queryset = queryset.prefetch_related(Prefetch("tasks", queryset=_recent_case_task_queryset()))
    if limit is not None:
        return queryset[:limit]
    return queryset


def _recent_task_action_flags(task, *, category_name, can_edit_tasks, today):
    is_future_anc = category_name.upper() == "ANC" and task.due_date > today
    return {
        "can_complete": can_edit_tasks and task.status != TaskStatus.COMPLETED and not is_future_anc,
        "can_reschedule": can_edit_tasks and task.status != TaskStatus.COMPLETED,
        "can_note": can_edit_tasks,
        "is_locked_until_due": is_future_anc and task.status != TaskStatus.COMPLETED,
    }


def _serialize_recent_task(task, *, category_name, can_edit_tasks, today):
    action_flags = _recent_task_action_flags(
        task,
        category_name=category_name,
        can_edit_tasks=can_edit_tasks,
        today=today,
    )
    return {
        "id": task.id,
        "title": task.title,
        "due_date": task.due_date.isoformat(),
        "due_date_display": task.due_date.strftime("%d %b %Y"),
        "status": task.status,
        "status_label": task.get_status_display(),
        "notes": task.notes or "",
        **action_flags,
        "edit_url": reverse("patients:task_edit", kwargs={"pk": task.pk}),
    }


def _serialize_recent_case(case, user, *, today=None, can_edit_recent=None, can_edit_tasks=None):
    if today is None:
        today = timezone.localdate()
    created_local = timezone.localtime(case.created_at)
    diagnosis = (case.diagnosis or case.category.name).strip()
    if can_edit_recent is None:
        can_edit_recent = _can_edit_recent_cases(user)
    if can_edit_tasks is None:
        can_edit_tasks = can_edit_recent and has_capability(user, "task_edit")
    category_name = case.category.name
    tasks = [
        _serialize_recent_task(task, category_name=category_name, can_edit_tasks=can_edit_tasks, today=today)
        for task in case.tasks.all()
    ]
    return {
        "id": case.id,
        "name": case.full_name or case.patient_name,
        "first_name": case.first_name or case.full_name or case.patient_name,
        "age_label": _case_age_label(case),
        "gender_label": case.get_gender_display() if case.gender else "-",
        "diagnosis": diagnosis,
        "diagnosis_short": _truncate_text(diagnosis),
        "notes": case.notes or "",
        "created_at": created_local.isoformat(),
        "created_at_display": created_local.strftime("%d %b %Y %H:%M"),
        "is_new_today": created_local.date() == today,
        "can_edit": can_edit_recent,
        "detail_url": reverse("patients:case_detail", kwargs={"pk": case.pk}),
        "tasks": tasks,
    }


def _serialize_recent_case_summary(case, user, *, today=None, can_edit_recent=None):
    if today is None:
        today = timezone.localdate()
    created_local = timezone.localtime(case.created_at)
    diagnosis = (case.diagnosis or case.category.name).strip()
    if can_edit_recent is None:
        can_edit_recent = _can_edit_recent_cases(user)
    return {
        "id": case.id,
        "name": case.full_name or case.patient_name,
        "first_name": case.first_name or case.full_name or case.patient_name,
        "age_label": _case_age_label(case),
        "gender_label": case.get_gender_display() if case.gender else "-",
        "diagnosis": diagnosis,
        "diagnosis_short": _truncate_text(diagnosis),
        "notes": case.notes or "",
        "created_at": created_local.isoformat(),
        "created_at_display": created_local.strftime("%d %b %Y %H:%M"),
        "is_new_today": created_local.date() == today,
        "can_edit": can_edit_recent,
        "detail_url": reverse("patients:case_detail", kwargs={"pk": case.pk}),
    }


def _recent_cases_payload_for_user(user, *, limit=RECENT_CASE_LIMIT_DEFAULT):
    today = timezone.localdate()
    can_edit_recent = _can_edit_recent_cases(user)
    can_edit_tasks = can_edit_recent and has_capability(user, "task_edit")
    return [
        _serialize_recent_case(
            case,
            user,
            today=today,
            can_edit_recent=can_edit_recent,
            can_edit_tasks=can_edit_tasks,
        )
        for case in _recent_case_queryset(limit=limit)
    ]


def _recent_case_summary_payload_for_user(user, *, limit=RECENT_CASE_LIMIT_DEFAULT):
    today = timezone.localdate()
    can_edit_recent = _can_edit_recent_cases(user)
    return [
        _serialize_recent_case_summary(case, user, today=today, can_edit_recent=can_edit_recent)
        for case in _recent_case_queryset(limit=limit, include_tasks=False)
    ]


def _recent_case_payload_for_id(case_id, user):
    today = timezone.localdate()
    case = get_object_or_404(_recent_case_queryset(include_tasks=True), pk=case_id)
    can_edit_recent = _can_edit_recent_cases(user)
    can_edit_tasks = can_edit_recent and has_capability(user, "task_edit")
    return _serialize_recent_case(
        case,
        user,
        today=today,
        can_edit_recent=can_edit_recent,
        can_edit_tasks=can_edit_tasks,
    )


def _task_action_error_response(request, *, case_id, message, status=400):
    if _request_wants_json(request):
        return JsonResponse({"message": message}, status=status)
    messages.error(request, message)
    return redirect("patients:case_detail", pk=case_id)


def _task_action_success_response(request, *, task, message):
    if _request_wants_json(request):
        payload = {
            "message": message,
            "task": _serialize_recent_task(
                task,
                category_name=task.case.category.name,
                can_edit_tasks=_can_edit_recent_cases(request.user) and has_capability(request.user, "task_edit"),
                today=timezone.localdate(),
            ),
        }
        if _can_view_recent_cases(request.user):
            payload["case"] = _recent_case_payload_for_id(task.case_id, request.user)
        return JsonResponse(payload)
    messages.success(request, message)
    return redirect("patients:case_detail", pk=task.case_id)


def _complete_task_inline(task, *, user):
    case = task.case
    if case.category.name.upper() == "ANC" and task.due_date > timezone.localdate():
        return False, "This ANC task is locked until its due date."

    task.status = TaskStatus.COMPLETED
    try:
        task.full_clean()
        task.save()
    except ValidationError:
        return False, "Could not complete task. Please review task state."

    create_case_activity(
        case=case,
        task=task,
        user=user,
        event_type=ActivityEventType.TASK,
        note=f"Task completed: {task.title}",
    )
    return True, "Task marked as completed."


def _reschedule_task_inline(task, *, due_date_raw, user):
    if task.status == TaskStatus.COMPLETED:
        return False, "Completed tasks cannot be rescheduled inline."
    if not due_date_raw:
        return False, "Please provide a new due date."

    try:
        new_due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
    except ValueError:
        return False, "Please enter a valid due date."

    old_due_date = task.due_date
    task.due_date = new_due_date
    try:
        task.full_clean()
        task.save()
    except ValidationError:
        return False, "Could not reschedule task. Please check the date."

    create_case_activity(
        case=task.case,
        task=task,
        user=user,
        event_type=ActivityEventType.TASK,
        note=f"Task rescheduled: {task.title} ({old_due_date:%d-%m-%Y} -> {new_due_date:%d-%m-%Y})",
    )
    return True, "Task rescheduled."


def _save_task_note_inline(task, *, note_text, user):
    if not note_text:
        return False, "Task note cannot be empty."

    task.notes = note_text
    task.save(update_fields=["notes", "updated_at"])
    create_case_activity(
        case=task.case,
        task=task,
        user=user,
        event_type=ActivityEventType.TASK,
        note=f"{note_text} [Task: {task.title}]",
    )
    return True, "Task note saved."


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


def _normalized_timeline_filter(raw_value):
    if raw_value in {"all", "calls", "tasks", "notes"}:
        return raw_value
    return "all"


def _normalized_category_style(category_name):
    normalized = (category_name or "").strip().lower().replace("-", " ")
    if normalized == "anc":
        return "anc"
    if normalized == "surgery":
        return "surgery"
    if normalized in {"non surgical", "nonsurgical"}:
        return "non-surgical"
    return "other"


def _normalized_gender_style(gender_value):
    if gender_value == Gender.FEMALE:
        return "female"
    if gender_value == Gender.MALE:
        return "male"
    return "other"


def _case_age_label(case):
    if case.age is not None:
        return f"{case.age}Y"
    if case.date_of_birth:
        today = timezone.localdate()
        years = today.year - case.date_of_birth.year - (
            (today.month, today.day) < (case.date_of_birth.month, case.date_of_birth.day)
        )
        return f"{max(years, 0)}Y"
    return "-"


def _case_initials(case):
    parts = [part[0].upper() for part in case.full_name.split() if part]
    if len(parts) >= 2:
        return "".join(parts[:2])
    compact_name = "".join(character for character in case.full_name if character.isalpha()).upper()
    if len(compact_name) >= 2:
        return compact_name[:2]
    if compact_name:
        return compact_name
    return "--"


def _case_name_size_class(case):
    name_length = len(case.full_name)
    if name_length >= 34:
        return "identity-name--compressed"
    if name_length >= 24:
        return "identity-name--compact"
    return ""


def _group_tasks_by_month(tasks):
    grouped = OrderedDict()
    for task in tasks:
        month_label = task.due_date.strftime("%b %Y")
        grouped.setdefault(month_label, []).append(task)
    return [{"label": month, "tasks": items} for month, items in grouped.items()]


def _build_actionable_task_sections(tasks, today, prominent_limit=5):
    open_tasks = [task for task in tasks if task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}]
    open_tasks.sort(key=lambda task: (task.due_date, task.id))
    overdue = [task for task in open_tasks if task.due_date < today]
    upcoming = [task for task in open_tasks if task.due_date >= today]

    prominent_tasks = list(overdue)
    remaining_slots = max(prominent_limit - len(prominent_tasks), 0)
    prominent_tasks.extend(upcoming[:remaining_slots])
    prominent_ids = {task.id for task in prominent_tasks}
    remaining_open_tasks = [task for task in open_tasks if task.id not in prominent_ids]

    history_tasks = [task for task in tasks if task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}]
    history_tasks.sort(key=lambda task: (task.due_date, task.id), reverse=True)
    for task in history_tasks:
        if task.status == TaskStatus.COMPLETED and task.completed_at:
            task.history_date_display = timezone.localtime(task.completed_at).strftime("%d-%m-%y")
        else:
            task.history_date_display = task.due_date.strftime("%d-%m-%y")
    return {
        "prominent_tasks": prominent_tasks,
        "remaining_open_groups": _group_tasks_by_month(remaining_open_tasks),
        "history_groups": _group_tasks_by_month(history_tasks),
        "open_count": len(open_tasks),
        "completed_count": len([task for task in tasks if task.status == TaskStatus.COMPLETED]),
    }


def _build_task_call_summary(call_logs):
    summary_by_task = {}
    for call in call_logs:
        if not call.task_id or call.task_id in summary_by_task:
            continue
        summary_by_task[call.task_id] = {
            "outcome": call.get_outcome_display(),
            "logged_at": timezone.localtime(call.created_at),
        }
    return summary_by_task


def _build_timeline_entries(*, call_logs, activity_logs, timeline_filter):
    entries = []
    if timeline_filter in {"all", "calls"}:
        for call in call_logs:
            entries.append(
                {
                    "event_type": "CALL",
                    "event_label": "Call",
                    "timestamp": call.created_at,
                    "timestamp_local": timezone.localtime(call.created_at),
                    "actor": str(call.staff_user) if call.staff_user else "system",
                    "task_title": call.task.title if call.task_id else "",
                    "headline": call.get_outcome_display(),
                    "details": call.notes,
                }
            )

    if timeline_filter in {"all", "tasks", "notes"}:
        for activity in activity_logs:
            if activity.event_type == ActivityEventType.CALL:
                continue
            if timeline_filter == "tasks" and activity.event_type != ActivityEventType.TASK:
                continue
            is_task_note = (
                activity.event_type == ActivityEventType.TASK
                and activity.task_id is not None
                and (
                    TASK_NOTE_MARKER in (activity.note or "")
                    or (activity.note or "").startswith(LEGACY_TASK_NOTE_PREFIX)
                )
            )
            if timeline_filter == "notes" and activity.event_type != ActivityEventType.NOTE and not is_task_note:
                continue
            entries.append(
                {
                    "event_type": activity.event_type,
                    "event_label": "Note" if is_task_note else activity.get_event_type_display(),
                    "timestamp": activity.created_at,
                    "timestamp_local": timezone.localtime(activity.created_at),
                    "actor": str(activity.user) if activity.user else "system",
                    "task_title": activity.task.title if activity.task_id else "",
                    "headline": activity.note,
                    "details": "",
                }
            )

    entries.sort(key=lambda item: item["timestamp"], reverse=True)
    return entries


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
        "case__category__theme_bg_color",
        "case__category__theme_text_color",
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

    @staticmethod
    def _category_theme_payload(category):
        category_name = getattr(category, "name", "") or ""
        default_theme = get_default_category_theme(category_name)
        bg_color = getattr(category, "theme_bg_color", "") or default_theme["bg"]
        text_color = getattr(category, "theme_text_color", "") or default_theme["text"]
        return {
            "name": category_name,
            "bg_color": bg_color,
            "text_color": text_color,
            "dot_color": mix_colors(text_color, bg_color, 0.22),
        }

    @classmethod
    def _build_appointment_schedule_days(cls, task_queryset, today, upcoming_days):
        grouped_tasks = OrderedDict()
        for task in task_queryset:
            day_groups = grouped_tasks.setdefault(task.due_date, OrderedDict())
            day_groups.setdefault(task.case_id, []).append(task)

        schedule_days = []
        for offset in range(upcoming_days + 1):
            schedule_date = today + timedelta(days=offset)
            case_groups = grouped_tasks.get(schedule_date, OrderedDict())
            category_map = OrderedDict()
            rows = []

            for grouped in case_groups.values():
                first_task = grouped[0]
                case = first_task.case
                category_theme = cls._category_theme_payload(case.category)
                category_map.setdefault(case.category.name, category_theme)

                unique_titles = []
                seen_titles = set()
                for task in grouped:
                    if task.title in seen_titles:
                        continue
                    seen_titles.add(task.title)
                    unique_titles.append(task.title)

                rows.append(
                    {
                        "case_id": case.id,
                        "patient_name": case.full_name or case.patient_name,
                        "diagnosis": case.diagnosis or case.category.name,
                        "task_titles": unique_titles,
                        "category_name": category_theme["name"],
                        "category_bg_color": category_theme["bg_color"],
                        "category_text_color": category_theme["text_color"],
                    }
                )

            rows.sort(key=lambda item: ((item["patient_name"] or "").lower(), item["case_id"]))
            categories = sorted(category_map.values(), key=lambda item: item["name"].lower())
            schedule_days.append(
                {
                    "date": schedule_date,
                    "date_key": schedule_date.isoformat(),
                    "count": len(rows),
                    "categories": categories,
                    "rows": rows,
                    "is_selected": offset == 0,
                }
            )

        return schedule_days

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
        context["appointment_schedule_days"] = self._build_appointment_schedule_days(
            [*today_tasks, *upcoming_tasks],
            today,
            upcoming_days,
        )
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
        context["show_recent_cases_panel"] = _can_view_recent_cases(self.request.user)
        context["can_edit_recent_cases"] = _can_edit_recent_cases(self.request.user)
        context["recent_cases"] = (
            _recent_case_summary_payload_for_user(self.request.user, limit=RECENT_CASE_LIMIT_DEFAULT)
            if context["show_recent_cases_panel"]
            else []
        )
        return context


class RecentCasesView(LoginRequiredMixin, CaseDataAccessMixin, View):
    def get(self, request):
        if not _can_view_recent_cases(request.user):
            return _forbidden_response(request, "You do not have permission to view recent cases.")

        limit = _clamp_recent_case_limit(request.GET.get("limit", RECENT_CASE_LIMIT_DEFAULT))
        return JsonResponse({"results": _recent_cases_payload_for_user(request.user, limit=limit)})


class RecentCaseUpdateView(LoginRequiredMixin, CaseDataAccessMixin, View):
    def post(self, request, pk):
        if not _can_view_recent_cases(request.user):
            return _forbidden_response(request, "You do not have permission to view recent cases.")
        if not _can_edit_recent_cases(request.user):
            return _forbidden_response(request, "You do not have permission to edit recent cases.")

        case = get_object_or_404(Case.objects.select_related("category"), pk=pk)
        old_diagnosis = case.diagnosis or ""
        old_notes = case.notes or ""
        form = RecentCaseUpdateForm(request.POST, instance=case)
        if not form.is_valid():
            return JsonResponse({"message": "Could not save case.", "errors": form.errors.get_json_data()}, status=400)

        new_diagnosis = form.cleaned_data.get("diagnosis", "") or ""
        new_notes = form.cleaned_data.get("notes", "") or ""
        diagnosis_changed = old_diagnosis != new_diagnosis
        notes_changed = old_notes != new_notes

        if diagnosis_changed or notes_changed:
            form.save()
            if diagnosis_changed:
                previous_label = old_diagnosis or "blank"
                current_label = new_diagnosis or "blank"
                create_case_activity(
                    case=case,
                    user=request.user,
                    event_type=ActivityEventType.SYSTEM,
                    note=f"Diagnosis updated: {previous_label} -> {current_label}",
                )
            if notes_changed:
                create_case_activity(
                    case=case,
                    user=request.user,
                    event_type=ActivityEventType.NOTE,
                    note=new_notes or "Case notes cleared.",
                )
            message = "Recent case updated."
        else:
            message = "No changes to save."

        return JsonResponse({"message": message, "case": _recent_case_payload_for_id(pk, request.user)})


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
                "category__theme_bg_color",
                "category__theme_text_color",
                "gender",
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
        theme_category_colors = build_theme_category_colors(
            [case.category for case in top_cases if getattr(case, "category", None) is not None]
        )

        results = []
        for case in top_cases:
            diagnosis = self._normalized(case.diagnosis) or "\u2014"
            village = self._normalized(case.place) or "\u2014"
            age = case.age if case.age is not None else "\u2014"
            category = case.category.name
            category_style = _normalized_category_style(category)
            category_theme = resolve_category_theme(theme_category_colors, case.category)
            gender_style = _normalized_gender_style(case.gender)
            tags = [
                {
                    "kind": "category",
                    "label": category,
                    "value": category_style,
                    "bg_color": category_theme["bg"],
                    "text_color": category_theme["text"],
                    "border_color": category_theme["border"],
                },
            ]
            if case.gender:
                tags.append({"kind": "gender", "label": case.get_gender_display(), "value": gender_style})
            if case.high_risk:
                tags.append({"kind": "high_risk", "label": "High-risk", "icon": "\u2757"})
            if case.referred_by:
                tags.append({"kind": "referred", "label": "Referred", "icon": "\u2b50"})
            if case.ncd_flags:
                tags.append({"kind": "ncd", "label": "NCD", "icon": "\U0001f3f7\ufe0f"})

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
        create_case_activity(
            case=self.object,
            user=self.request.user,
            event_type=ActivityEventType.SYSTEM,
            note=f"Case created with {len(created_tasks)} starter task(s)",
        )
        reminder = ensure_rch_reminder_task(self.object, self.request.user)
        if reminder:
            create_case_activity(
                case=self.object,
                task=reminder,
                user=self.request.user,
                event_type=ActivityEventType.TASK,
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
        tasks = list(case.tasks.select_related("assigned_user").order_by("due_date", "id"))
        call_logs = list(case.call_logs.select_related("staff_user", "task").order_by("-created_at", "-id"))
        activity_logs = list(case.activity_logs.select_related("user", "task").order_by("-created_at", "-id")[:200])
        latest_vital = case.vitals.order_by("-recorded_at", "-id").first()
        today = timezone.localdate()
        task_sections = _build_actionable_task_sections(tasks, today, prominent_limit=5)
        total_tasks = len(tasks)
        completed_tasks = task_sections["completed_count"]
        timeline_filter = _normalized_timeline_filter(self.request.GET.get("timeline", "all"))

        context["today"] = today
        context["tasks"] = tasks
        context["prominent_tasks"] = task_sections["prominent_tasks"]
        context["remaining_open_groups"] = task_sections["remaining_open_groups"]
        context["history_groups"] = task_sections["history_groups"]
        task_call_summary = _build_task_call_summary(call_logs)
        for task in tasks:
            task.latest_call_summary = task_call_summary.get(task.id)
        context["task_call_summary"] = task_call_summary
        context["has_vitals"] = latest_vital is not None
        context["latest_vitals_recorded_at"] = timezone.localtime(latest_vital.recorded_at) if latest_vital else None
        context["vitals_summary_metrics"] = _build_latest_vitals_summary(latest_vital)
        context["vitals_detail_url"] = reverse("patients:case_vitals", kwargs={"pk": case.pk})
        context["case_age_label"] = _case_age_label(case)
        context["case_initials"] = _case_initials(case)
        context["case_name_size_class"] = _case_name_size_class(case)
        context["completed_task_count"] = completed_tasks
        context["total_task_count"] = total_tasks
        context["progress_percent"] = round((completed_tasks / total_tasks) * 100) if total_tasks else 0
        context["progress_class"] = "bg-success" if context["progress_percent"] >= 50 else "bg-warning"
        context["timeline_filter_options"] = TIMELINE_FILTER_OPTIONS
        context["timeline_filter"] = timeline_filter
        context["timeline_entries"] = _build_timeline_entries(
            call_logs=call_logs,
            activity_logs=activity_logs,
            timeline_filter=timeline_filter,
        )
        context["timeline_collapsed"] = self.request.GET.get("show_logs") != "1"
        context["logs_url"] = f"{reverse('patients:case_detail', kwargs={'pk': case.pk})}?show_logs=1#clinical-timeline"
        context["task_form"] = TaskForm()
        context["log_form"] = ActivityLogForm()
        call_log_form = CallLogForm()
        call_log_form.fields["task"].queryset = case.tasks.order_by("due_date", "id")
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
            create_case_activity(
                case=case,
                user=self.request.user,
                event_type=ActivityEventType.SYSTEM,
                note=f"Case status changed: {old_status} -> {new_status}",
            )
        response = super().form_valid(form)
        if not is_anc_case(self.object):
            cancelled_count = cancel_open_rch_reminders(self.object)
            if cancelled_count:
                create_case_activity(
                    case=self.object,
                    user=self.request.user,
                    event_type=ActivityEventType.TASK,
                    note=f"Cancelled {cancelled_count} open RCH reminder task(s) because category is no longer ANC.",
                )
            return response

        if self.object.rch_number:
            cancelled_count = cancel_open_rch_reminders(self.object)
            if cancelled_count:
                create_case_activity(
                    case=self.object,
                    user=self.request.user,
                    event_type=ActivityEventType.TASK,
                    note=f"RCH number captured. Cancelled {cancelled_count} open RCH reminder task(s).",
                )
        else:
            reminder = ensure_rch_reminder_task(self.object, self.request.user)
            if reminder:
                create_case_activity(
                    case=self.object,
                    task=reminder,
                    user=self.request.user,
                    event_type=ActivityEventType.TASK,
                    note=f"RCH reminder scheduled for {reminder.due_date:%d-%m-%Y}.",
                )
        if had_rch_number and not self.object.rch_number:
            reminder = ensure_rch_reminder_task(self.object, self.request.user)
            if reminder:
                create_case_activity(
                    case=self.object,
                    task=reminder,
                    user=self.request.user,
                    event_type=ActivityEventType.TASK,
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
                create_case_activity(
                    case=case,
                    task=task,
                    user=request.user,
                    event_type=ActivityEventType.TASK,
                    note=f"Task created: {task.title}",
                )
                messages.success(request, "Task added.")
        else:
            messages.error(request, "Could not add task. Please check the inputs.")
        return redirect("patients:case_detail", pk=pk)


class TaskQuickCompleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return _forbidden_response(request, "You do not have permission to edit tasks.")

        task = get_object_or_404(Task.objects.select_related("case", "case__category"), pk=pk)
        success, message = _complete_task_inline(task, user=request.user)
        if not success:
            return _task_action_error_response(request, case_id=task.case_id, message=message)
        return _task_action_success_response(request, task=task, message=message)


class TaskQuickRescheduleView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return _forbidden_response(request, "You do not have permission to edit tasks.")

        task = get_object_or_404(Task.objects.select_related("case", "case__category"), pk=pk)
        success, message = _reschedule_task_inline(
            task,
            due_date_raw=(request.POST.get("due_date") or "").strip(),
            user=request.user,
        )
        if not success:
            return _task_action_error_response(request, case_id=task.case_id, message=message)
        return _task_action_success_response(request, task=task, message=message)


class TaskQuickNoteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not has_capability(request.user, "task_edit"):
            return _forbidden_response(request, "You do not have permission to edit tasks.")

        task = get_object_or_404(Task.objects.select_related("case", "case__category"), pk=pk)
        success, message = _save_task_note_inline(
            task,
            note_text=(request.POST.get("note") or "").strip(),
            user=request.user,
        )
        if not success:
            return _task_action_error_response(request, case_id=task.case_id, message=message)
        return _task_action_success_response(request, task=task, message=message)


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
        create_case_activity(
            case=self.object.case,
            task=self.object,
            user=self.request.user,
            event_type=ActivityEventType.TASK,
            note=f"Task updated: {self.object.title} ({self.object.status})",
        )
        if (
            previous_status != TaskStatus.COMPLETED
            and self.object.status == TaskStatus.COMPLETED
            and self.object.title == RCH_REMINDER_TASK_TITLE
        ):
            completed_local = timezone.localtime(self.object.completed_at) if self.object.completed_at else timezone.now()
            next_due_date = completed_local.date() + timedelta(days=RCH_REMINDER_INTERVAL_DAYS)
            reminder = ensure_rch_reminder_task(self.object.case, self.request.user, due_date=next_due_date)
            if reminder:
                create_case_activity(
                    case=self.object.case,
                    task=reminder,
                    user=self.request.user,
                    event_type=ActivityEventType.TASK,
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
            log.event_type = ActivityEventType.NOTE
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
            create_case_activity(
                case=case,
                task=log.task,
                user=request.user,
                event_type=ActivityEventType.CALL,
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
            create_case_activity(
                case=case,
                user=request.user,
                event_type=ActivityEventType.SYSTEM,
                note="Vitals entry recorded.",
            )
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
            create_case_activity(
                case=updated_vital.case,
                user=request.user,
                event_type=ActivityEventType.SYSTEM,
                note="Vitals entry updated.",
            )
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

class DeviceAwareLoginView(LoginView):
    template_name = "registration/login.html"

    def form_valid(self, form):
        user = form.get_user()
        if not _is_device_approval_target_user(user):
            return super().form_valid(form)

        trusted_credential = _get_trusted_device_credential(self.request, user)
        if trusted_credential:
            trusted_credential.last_used_at = timezone.now()
            trusted_credential.save(update_fields=["last_used_at"])
            return super().form_valid(form)

        _set_pending_device_login(
            self.request,
            user=user,
            backend=getattr(user, "backend", None),
            redirect_to=self.get_success_url(),
        )
        messages.info(
            self.request,
            "This account requires an approved device. Verify or register this browser to continue.",
        )
        return redirect("login_device_verification")


class DeviceVerificationView(View):
    template_name = "registration/device_verification.html"

    def get(self, request):
        user = _pending_device_login_user(request)
        if not user:
            messages.error(request, "Your login session expired. Sign in again.")
            return redirect("login")

        pending_devices = StaffDeviceCredential.objects.filter(
            user=user,
            status=StaffDeviceCredentialStatus.PENDING,
        ).order_by("-created_at")
        approved_devices = _approved_device_queryset(user).order_by("-last_used_at", "-approved_at", "-created_at")
        context = {
            "pending_user": user,
            "pending_devices": pending_devices,
            "approved_devices": approved_devices,
            "approved_device_count": approved_devices.count(),
            "max_approved_devices": DEVICE_APPROVAL_MAX_APPROVED,
            "can_register_device": _can_register_device(user),
            "has_approved_devices": approved_devices.exists(),
        }
        return render(request, self.template_name, context)


class DeviceRegistrationOptionsView(View):
    def post(self, request):
        user = _pending_device_login_user(request)
        if not user:
            return _pending_device_json_error("Your login session expired. Sign in again.", status=403)
        if not _is_device_approval_target_user(user):
            return _pending_device_json_error("This account no longer requires device approval. Sign in again.", status=403)
        if not _can_register_device(user):
            return _pending_device_json_error(
                f"This account already has {DEVICE_APPROVAL_MAX_APPROVED} approved devices. Ask an admin to revoke one first.",
                status=400,
            )

        deps = _load_webauthn_dependencies()
        registered_credentials = StaffDeviceCredential.objects.filter(user=user).exclude(
            status=StaffDeviceCredentialStatus.REVOKED
        )
        options = deps["generate_registration_options"](
            rp_id=_expected_webauthn_rp_id(request),
            rp_name=settings.WEBAUTHN_RP_NAME,
            user_id=str(user.pk).encode("utf-8"),
            user_name=user.username,
            user_display_name=user.get_full_name() or user.username,
            exclude_credentials=[_credential_descriptor_from_record(record, deps) for record in registered_credentials],
        )
        request.session[DEVICE_REGISTRATION_STATE_SESSION_KEY] = {
            "user_id": user.pk,
            "challenge": _bytes_to_base64url(options.challenge),
        }
        return JsonResponse(json.loads(deps["options_to_json"](options)))


class DeviceRegistrationVerifyView(View):
    def post(self, request):
        user = _pending_device_login_user(request)
        state = request.session.get(DEVICE_REGISTRATION_STATE_SESSION_KEY)
        if not user or not state or state.get("user_id") != user.pk:
            return _pending_device_json_error("Your device registration session expired. Sign in again.", status=403)

        payload = _parse_request_json(request)
        if payload is None:
            return _pending_device_json_error("Invalid registration payload.")
        if not _can_register_device(user):
            return _pending_device_json_error(
                f"This account already has {DEVICE_APPROVAL_MAX_APPROVED} approved devices. Ask an admin to revoke one first.",
                status=400,
            )

        device_label = (payload.get("device_label") or "").strip()
        if not device_label:
            device_label = f"{user.username} browser"
        credential_payload = payload.get("credential")
        if not isinstance(credential_payload, dict):
            return _pending_device_json_error("Missing credential registration data.")

        deps = _load_webauthn_dependencies()
        try:
            verification = deps["verify_registration_response"](
                credential=credential_payload,
                expected_challenge=deps["base64url_to_bytes"](state["challenge"]),
                expected_origin=_expected_webauthn_origin(request),
                expected_rp_id=_expected_webauthn_rp_id(request),
                require_user_verification=True,
            )
        except Exception as exc:
            return _pending_device_json_error(f"Device registration could not be verified: {exc}")

        credential_id = _bytes_to_base64url(verification.credential_id)
        existing = StaffDeviceCredential.objects.filter(credential_id=credential_id).first()
        if existing and existing.user_id != user.pk:
            return _pending_device_json_error("That device is already registered to another user.")
        if existing and existing.status == StaffDeviceCredentialStatus.APPROVED:
            return _pending_device_json_error("This device is already approved. Use device verification instead.")
        if existing and existing.status == StaffDeviceCredentialStatus.PENDING:
            return JsonResponse({"message": "This device is already awaiting admin approval.", "status": "PENDING"})

        aaguid = getattr(verification, "aaguid", "") or ""
        if isinstance(aaguid, bytes):
            aaguid = _bytes_to_base64url(aaguid)
        transports = credential_payload.get("transports") or []
        if not isinstance(transports, list):
            transports = []

        device = existing or StaffDeviceCredential(user=user, credential_id=credential_id)
        device.user = user
        device.status = StaffDeviceCredentialStatus.PENDING
        device.device_label = device_label[:120]
        device.public_key = _bytes_to_base64url(verification.credential_public_key)
        device.sign_count = getattr(verification, "sign_count", 0) or 0
        device.credential_type = (credential_payload.get("type") or "public-key")[:32]
        device.aaguid = str(aaguid)[:64]
        device.transports = transports
        device.authenticator_attachment = (credential_payload.get("authenticatorAttachment") or "")[:32]
        device.device_type = str(getattr(verification, "credential_device_type", "") or "")[:32]
        device.backed_up = bool(getattr(verification, "credential_backed_up", False))
        device.user_agent = request.META.get("HTTP_USER_AGENT", "")
        device.approved_at = None
        device.approved_by = None
        device.revoked_at = None
        device.revoked_by = None
        device.last_used_at = None
        device.clear_trusted_token()
        device.save()
        request.session.pop(DEVICE_REGISTRATION_STATE_SESSION_KEY, None)
        return JsonResponse(
            {
                "message": "Device registered. An admin must approve it before you can sign in from this browser.",
                "status": StaffDeviceCredentialStatus.PENDING,
            }
        )


class DeviceAuthenticationOptionsView(View):
    def post(self, request):
        user = _pending_device_login_user(request)
        if not user:
            return _pending_device_json_error("Your login session expired. Sign in again.", status=403)

        approved_devices = list(_approved_device_queryset(user).order_by("id"))
        if not approved_devices:
            return _pending_device_json_error("No approved devices are available for this account yet.", status=400)

        deps = _load_webauthn_dependencies()
        options = deps["generate_authentication_options"](
            rp_id=_expected_webauthn_rp_id(request),
            allow_credentials=[_credential_descriptor_from_record(record, deps) for record in approved_devices],
            user_verification=deps["UserVerificationRequirement"].REQUIRED,
        )
        request.session[DEVICE_AUTHENTICATION_STATE_SESSION_KEY] = {
            "user_id": user.pk,
            "challenge": _bytes_to_base64url(options.challenge),
        }
        return JsonResponse(json.loads(deps["options_to_json"](options)))


class DeviceAuthenticationVerifyView(View):
    def post(self, request):
        user = _pending_device_login_user(request)
        login_state = _pending_device_login_state(request)
        auth_state = request.session.get(DEVICE_AUTHENTICATION_STATE_SESSION_KEY)
        if not user or not login_state or not auth_state or auth_state.get("user_id") != user.pk:
            return _pending_device_json_error("Your device verification session expired. Sign in again.", status=403)

        payload = _parse_request_json(request)
        if payload is None:
            return _pending_device_json_error("Invalid verification payload.")
        credential_payload = payload.get("credential")
        if not isinstance(credential_payload, dict):
            return _pending_device_json_error("Missing credential verification data.")

        credential_id = credential_payload.get("id")
        if not credential_id:
            return _pending_device_json_error("Missing credential identifier.")

        device = _approved_device_queryset(user).filter(credential_id=credential_id).first()
        if not device:
            return _pending_device_json_error("That device is not approved for this account.", status=403)

        deps = _load_webauthn_dependencies()
        try:
            verification = deps["verify_authentication_response"](
                credential=credential_payload,
                expected_challenge=deps["base64url_to_bytes"](auth_state["challenge"]),
                expected_rp_id=_expected_webauthn_rp_id(request),
                expected_origin=_expected_webauthn_origin(request),
                credential_public_key=deps["base64url_to_bytes"](device.public_key),
                credential_current_sign_count=device.sign_count,
                require_user_verification=True,
            )
        except Exception as exc:
            return _pending_device_json_error(f"Device verification failed: {exc}")

        device.sign_count = getattr(verification, "new_sign_count", device.sign_count)
        device.last_used_at = timezone.now()
        device.user_agent = request.META.get("HTTP_USER_AGENT", "")
        device.save(update_fields=["sign_count", "last_used_at", "user_agent"])

        redirect_to = login_state.get("redirect_to") or reverse("patients:dashboard")
        backend = login_state.get("backend") or settings.AUTHENTICATION_BACKENDS[0]
        _clear_pending_device_login(request)
        auth_login(request, user, backend=backend)
        response = JsonResponse({"message": "Device verified.", "redirect_url": redirect_to})
        _set_trusted_device_cookie(response, device)
        return response


class DeviceAccessSettingsView(LoginRequiredMixin, View):
    template_name = "patients/settings_device_access.html"

    def _check_access(self, request):
        if not has_capability(request.user, "manage_settings"):
            return HttpResponseForbidden("Only admins can access settings.")
        return None

    def _build_context(self, policy_form):
        return {
            "policy_form": policy_form,
            "pending_devices": StaffDeviceCredential.objects.select_related("user").filter(
                status=StaffDeviceCredentialStatus.PENDING
            ).order_by("user__username", "-created_at"),
            "approved_devices": StaffDeviceCredential.objects.select_related("user").filter(
                status=StaffDeviceCredentialStatus.APPROVED
            ).order_by("user__username", "-approved_at", "-created_at"),
            "max_approved_devices": DEVICE_APPROVAL_MAX_APPROVED,
            "staff_role_name": STAFF_ROLE_NAME,
            "staff_pilot_role_name": STAFF_PILOT_ROLE_NAME,
        }

    def get(self, request):
        denied = self._check_access(request)
        if denied:
            return denied
        return render(request, self.template_name, self._build_context(DeviceApprovalPolicyForm(instance=_device_policy())))

    def post(self, request):
        denied = self._check_access(request)
        if denied:
            return denied

        action = request.POST.get("action", "save_policy")
        policy = _device_policy()

        if action == "save_policy":
            form = DeviceApprovalPolicyForm(request.POST, instance=policy)
            if form.is_valid():
                form.save()
                messages.success(request, "Device approval pilot settings saved.")
                return redirect("patients:settings_device_access")
            messages.error(request, "Device approval settings have errors.")
            return render(request, self.template_name, self._build_context(form))

        if action == "clone_staff_pilot":
            try:
                pilot_role = clone_role_setting()
            except RoleSetting.DoesNotExist:
                messages.error(request, f"Source role {STAFF_ROLE_NAME} does not exist yet.")
            else:
                Group.objects.get_or_create(name=pilot_role.role_name)
                messages.success(request, f"Created or refreshed the {pilot_role.role_name} role from {STAFF_ROLE_NAME}.")
            return redirect("patients:settings_device_access")

        credential = get_object_or_404(StaffDeviceCredential.objects.select_related("user"), pk=request.POST.get("credential_id"))
        if action == "approve_device":
            if credential.status != StaffDeviceCredentialStatus.APPROVED and _approved_device_count(credential.user) >= DEVICE_APPROVAL_MAX_APPROVED:
                messages.error(
                    request,
                    f"{credential.user.username} already has {DEVICE_APPROVAL_MAX_APPROVED} approved devices. Revoke one before approving another.",
                )
                return redirect("patients:settings_device_access")
            credential.status = StaffDeviceCredentialStatus.APPROVED
            credential.approved_at = timezone.now()
            credential.approved_by = request.user
            credential.revoked_at = None
            credential.revoked_by = None
            credential.clear_trusted_token()
            credential.save(
                update_fields=[
                    "status",
                    "approved_at",
                    "approved_by",
                    "revoked_at",
                    "revoked_by",
                    "trusted_token_hash",
                    "trusted_token_created_at",
                ]
            )
            messages.success(request, f"Approved {credential.device_label} for {credential.user.username}.")
            return redirect("patients:settings_device_access")

        if action == "revoke_device":
            credential.status = StaffDeviceCredentialStatus.REVOKED
            credential.revoked_at = timezone.now()
            credential.revoked_by = request.user
            credential.clear_trusted_token()
            credential.save(
                update_fields=[
                    "status",
                    "revoked_at",
                    "revoked_by",
                    "trusted_token_hash",
                    "trusted_token_created_at",
                ]
            )
            messages.success(request, f"Revoked {credential.device_label} for {credential.user.username}.")
            return redirect("patients:settings_device_access")

        messages.error(request, "Unknown device access action.")
        return redirect("patients:settings_device_access")


class ChangelogView(LoginRequiredMixin, View):
    template_name = "patients/changelog.html"

    def get(self, request):
        if not has_capability(request.user, "manage_settings"):
            return HttpResponseForbidden("Only admins can access changelog.")

        context = {"changelog_entries": _load_changelog_entries()}
        return render(request, self.template_name, context)


class SeedMockDataSettingsView(LoginRequiredMixin, View):
    template_name = "patients/settings_seed_mock_data.html"

    def _check_access(self, request):
        if not has_capability(request.user, "manage_settings"):
            return HttpResponseForbidden("Only admins can access settings.")
        return None

    def get(self, request):
        denied = self._check_access(request)
        if denied:
            return denied
        context = {
            "form": SeedMockDataForm(initial={"profile": "full"}),
            "seeded_case_count": Case.objects.filter(metadata__source="seed_mock_data").count(),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        denied = self._check_access(request)
        if denied:
            return denied

        action = request.POST.get("action")
        form = SeedMockDataForm(request.POST)
        if action == "delete_seeded":
            delete_seeded_mock_data()
            messages.success(request, "Deleted seeded mock cases and their linked call/activity logs.")
            return redirect("patients:settings_seed_mock_data")

        if not form.is_valid():
            messages.error(request, f"Seed options have errors: {form.errors}")
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "seeded_case_count": Case.objects.filter(metadata__source="seed_mock_data").count(),
                },
            )

        command_args = ["seed_mock_data"]
        count = form.cleaned_data.get("count")
        profile = form.cleaned_data["profile"]
        if count:
            command_args.extend(["--count", str(count)])
        command_args.extend(["--profile", profile])
        if form.cleaned_data.get("include_vitals"):
            command_args.append("--include-vitals")
        if form.cleaned_data.get("include_rch_scenarios"):
            command_args.append("--include-rch-scenarios")
        if form.cleaned_data.get("reset_all"):
            if not form.cleaned_data.get("confirm_reset_all"):
                form.add_error("reset_all", "Please confirm reset-all before continuing.")
                messages.error(request, "Reset-all confirmation is required.")
                return render(
                    request,
                    self.template_name,
                    {
                        "form": form,
                        "seeded_case_count": Case.objects.filter(metadata__source="seed_mock_data").count(),
                    },
                )
            command_args.extend(["--reset-all", "--yes-reset-all"])
        elif action == "reseed":
            command_args.append("--reset")

        call_command(*command_args)
        messages.success(request, "Mock data seeding completed.")
        return redirect("patients:settings_seed_mock_data")


class ThemeSettingsView(LoginRequiredMixin, View):
    template_name = "patients/settings_theme.html"

    def _check_access(self, request):
        if not has_capability(request.user, "manage_settings"):
            return HttpResponseForbidden("Only admins can access settings.")
        return None

    @staticmethod
    def _formset_queryset():
        return DepartmentConfig.objects.order_by("name")

    def _build_context(self, theme_form, department_theme_formset):
        return {
            "theme_form": theme_form,
            "department_theme_formset": department_theme_formset,
            "theme_form_sections": theme_form.sections,
        }

    def get(self, request):
        denied = self._check_access(request)
        if denied:
            return denied
        theme_settings = ThemeSettings.get_solo()
        theme_form = ThemeSettingsForm(instance=theme_settings)
        department_theme_formset = DepartmentThemeFormSet(
            queryset=self._formset_queryset(),
            prefix="categories",
        )
        return render(request, self.template_name, self._build_context(theme_form, department_theme_formset))

    def post(self, request):
        denied = self._check_access(request)
        if denied:
            return denied

        action = request.POST.get("action", "save")
        if action == "restore_defaults":
            theme_settings = ThemeSettings.get_solo()
            theme_settings.tokens = {}
            theme_settings.save()
            for department in self._formset_queryset():
                default_theme = get_default_category_theme(department.name)
                department.theme_bg_color = default_theme["bg"]
                department.theme_text_color = default_theme["text"]
                department.save(update_fields=["theme_bg_color", "theme_text_color"])
            messages.success(request, "Theme restored to defaults.")
            return redirect("patients:settings_theme")

        theme_settings = ThemeSettings.get_solo()
        theme_form = ThemeSettingsForm(request.POST, instance=theme_settings)
        department_theme_formset = DepartmentThemeFormSet(
            request.POST,
            queryset=self._formset_queryset(),
            prefix="categories",
        )

        if theme_form.is_valid() and department_theme_formset.is_valid():
            theme_form.save()
            department_theme_formset.save()
            messages.success(request, "Theme settings saved.")
            return redirect("patients:settings_theme")

        messages.error(request, "Theme settings have errors.")
        return render(request, self.template_name, self._build_context(theme_form, department_theme_formset))


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
