from collections import OrderedDict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import ActivityLogForm, CaseForm, DepartmentConfigForm, RoleSettingForm, TaskForm, UserRoleForm
from .models import (
    Case,
    CaseActivityLog,
    CaseStatus,
    DepartmentConfig,
    RoleSetting,
    Task,
    TaskStatus,
    build_default_tasks,
    ensure_default_role_settings,
    frequency_to_days,
)


def has_capability(user, capability):
    if user.is_superuser:
        return True
    ensure_default_role_settings()
    user_groups = set(user.groups.values_list("name", flat=True))
    role_settings = {r.role_name: r for r in RoleSetting.objects.filter(role_name__in=user_groups)}
    for group in user_groups:
        role_setting = role_settings.get(group)
        if role_setting and role_setting.capabilities().get(capability, False):
            return True
    return False


def is_doctor_admin(user):
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Doctor", "Admin"]).exists()


class DashboardView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "patients/dashboard.html"
    context_object_name = "today_tasks"

    @staticmethod
    def _build_patient_day_cards(task_queryset):
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
                }
            )
        return cards

    def get_queryset(self):
        today = timezone.localdate()
        return Task.objects.select_related("case", "case__category", "assigned_user").filter(due_date=today, status=TaskStatus.SCHEDULED).order_by("due_date", "case_id", "id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        upcoming_days = int(self.request.GET.get("upcoming_days", 7))

        tasks = Task.objects.select_related("case", "case__category", "assigned_user")
        context["upcoming_tasks"] = tasks.filter(due_date__gt=today, due_date__lte=today + timedelta(days=upcoming_days), status=TaskStatus.SCHEDULED).order_by("due_date", "case_id", "id")
        context["overdue_tasks"] = tasks.exclude(status=TaskStatus.COMPLETED).filter(due_date__lt=today).order_by("due_date", "case_id", "id")
        context["awaiting_tasks"] = tasks.filter(status=TaskStatus.AWAITING_REPORTS)
        context["today_cards"] = self._build_patient_day_cards(context["today_tasks"])
        context["upcoming_cards"] = self._build_patient_day_cards(context["upcoming_tasks"])
        context["overdue_cards"] = self._build_patient_day_cards(context["overdue_tasks"])
        context["active_case_count"] = Case.objects.filter(status=CaseStatus.ACTIVE).count()
        context["completed_case_count"] = Case.objects.filter(status=CaseStatus.COMPLETED).count()
        context["upcoming_days"] = upcoming_days
        context["red_list_count"] = tasks.exclude(status=TaskStatus.COMPLETED).filter(due_date__lt=today, due_date__gte=today - timedelta(days=30)).count()
        context["grey_list_count"] = tasks.exclude(status=TaskStatus.COMPLETED).filter(due_date__lt=today - timedelta(days=30)).count()
        return context


class CaseListView(LoginRequiredMixin, ListView):
    model = Case
    template_name = "patients/case_list.html"
    context_object_name = "cases"

    def get_queryset(self):
        queryset = Case.objects.select_related("category")
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        category = self.request.GET.get("category", "").strip()
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
        if category:
            queryset = queryset.filter(category_id=category)
        if assigned_user:
            queryset = queryset.filter(tasks__assigned_user_id=assigned_user).distinct()
        if due_start:
            queryset = queryset.filter(tasks__due_date__gte=due_start).distinct()
        if due_end:
            queryset = queryset.filter(tasks__due_date__lte=due_end).distinct()

        return queryset.annotate(task_count=Count("tasks"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {k: self.request.GET.get(k, "") for k in ["q", "status", "category", "assigned_user", "due_start", "due_end"]}
        context["case_statuses"] = CaseStatus.choices
        context["categories"] = DepartmentConfig.objects.all()
        context["users"] = get_user_model().objects.order_by("username")
        return context


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
        context["today"] = timezone.localdate()
        context["activity_logs"] = case.activity_logs.select_related("user", "task")[:50]
        context["task_form"] = TaskForm()
        context["log_form"] = ActivityLogForm()
        context["can_task_create"] = has_capability(self.request.user, "task_create")
        context["can_task_edit"] = has_capability(self.request.user, "task_edit")
        context["can_note_add"] = has_capability(self.request.user, "note_add")
        return context

    def dispatch(self, request, *args, **kwargs):
        if not has_capability(request.user, "task_edit"):
            return HttpResponseForbidden("You do not have permission to edit tasks.")
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
        new_status = form.cleaned_data["status"]
        grey_list_cutoff = timezone.localdate() - timedelta(days=30)
        has_grey_tasks = case.tasks.exclude(status=TaskStatus.COMPLETED).filter(due_date__lt=grey_list_cutoff).exists()
        if has_grey_tasks and new_status in [CaseStatus.LOSS_TO_FOLLOW_UP, CaseStatus.ACTIVE] and not is_doctor_admin(self.request.user):
            form.add_error("status", "Only Doctor/Admin can set Grey List cases to Active or Loss to Follow-up.")
            return self.form_invalid(form)
        if old_status != new_status:
            CaseActivityLog.objects.create(case=case, user=self.request.user, note=f"Case status changed: {old_status} → {new_status}")
        return super().form_valid(form)

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
            task.save()
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
        response = super().form_valid(form)
        CaseActivityLog.objects.create(case=self.object.case, task=self.object, user=self.request.user, note=f"Task updated: {self.object.title} ({self.object.status})")
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
