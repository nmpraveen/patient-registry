from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import ActivityLogForm, CaseForm, TaskForm
from .models import Case, CaseActivityLog, CaseStatus, Task, TaskStatus


class DashboardView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "patients/dashboard.html"
    context_object_name = "today_tasks"

    def get_queryset(self):
        today = timezone.localdate()
        return Task.objects.select_related("case", "assigned_user").filter(due_date=today, status=TaskStatus.SCHEDULED)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        upcoming_days = int(self.request.GET.get("upcoming_days", 7))

        tasks = Task.objects.select_related("case", "assigned_user")
        context["upcoming_tasks"] = tasks.filter(
            due_date__gt=today,
            due_date__lte=today + timedelta(days=upcoming_days),
            status=TaskStatus.SCHEDULED,
        )
        context["overdue_tasks"] = tasks.exclude(status=TaskStatus.COMPLETED).filter(due_date__lt=today)
        context["awaiting_tasks"] = tasks.filter(status=TaskStatus.AWAITING_REPORTS)
        context["active_case_count"] = Case.objects.filter(status=CaseStatus.ACTIVE).count()
        context["completed_case_count"] = Case.objects.filter(status=CaseStatus.COMPLETED).count()
        context["upcoming_days"] = upcoming_days
        context["red_list_count"] = tasks.exclude(status=TaskStatus.COMPLETED).filter(
            due_date__lt=today, due_date__gte=today - timedelta(days=30)
        ).count()
        context["grey_list_count"] = tasks.exclude(status=TaskStatus.COMPLETED).filter(
            due_date__lt=today - timedelta(days=30)
        ).count()
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
            queryset = queryset.filter(Q(uhid__icontains=q) | Q(phone_number__icontains=q) | Q(patient_name__icontains=q))
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
        from django.contrib.auth import get_user_model
        from .models import DepartmentConfig

        context["categories"] = DepartmentConfig.objects.all()
        context["users"] = get_user_model().objects.order_by("username")
        return context


class CaseCreateView(LoginRequiredMixin, CreateView):
    model = Case
    form_class = CaseForm
    template_name = "patients/case_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        CaseActivityLog.objects.create(case=self.object, user=self.request.user, note="Case created")
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
        context["activity_logs"] = case.activity_logs.select_related("user", "task")[:50]
        context["task_form"] = TaskForm()
        log_form = ActivityLogForm()
        log_form.fields["task"].queryset = case.tasks.all()
        log_form.fields["task"].required = False
        context["log_form"] = log_form
        context["is_doctor"] = self.request.user.groups.filter(name__in=["Doctor", "Admin"]).exists() or self.request.user.is_superuser
        return context


class CaseUpdateView(LoginRequiredMixin, UpdateView):
    model = Case
    form_class = CaseForm
    template_name = "patients/case_form.html"

    def form_valid(self, form):
        case = self.get_object()
        old_status = case.status
        new_status = form.cleaned_data["status"]
        grey_list_cutoff = timezone.localdate() - timedelta(days=30)
        has_grey_tasks = case.tasks.exclude(status=TaskStatus.COMPLETED).filter(due_date__lt=grey_list_cutoff).exists()
        is_doctor = self.request.user.groups.filter(name__in=["Doctor", "Admin"]).exists() or self.request.user.is_superuser
        if has_grey_tasks and new_status in [CaseStatus.LOSS_TO_FOLLOW_UP, CaseStatus.ACTIVE] and not is_doctor:
            form.add_error("status", "Only Doctor/Admin can set Grey List cases to Active or Loss to Follow-up.")
            return self.form_invalid(form)
        if old_status != new_status:
            CaseActivityLog.objects.create(case=case, user=self.request.user, note=f"Case status changed: {old_status} → {new_status}")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("patients:case_detail", kwargs={"pk": self.object.pk})


class TaskCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
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

    def form_valid(self, form):
        response = super().form_valid(form)
        CaseActivityLog.objects.create(
            case=self.object.case,
            task=self.object,
            user=self.request.user,
            note=f"Task updated: {self.object.title} ({self.object.status})",
        )
        return response

    def get_success_url(self):
        return reverse("patients:case_detail", kwargs={"pk": self.object.case_id})


class AddCaseNoteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk)
        form = ActivityLogForm(request.POST)
        form.fields["task"].queryset = case.tasks.all()
        if form.is_valid():
            log = form.save(commit=False)
            log.case = case
            log.user = request.user
            if log.task and log.task.case_id != case.id:
                messages.error(request, "Selected task does not belong to this case.")
                return redirect("patients:case_detail", pk=pk)
            log.save()
            messages.success(request, "Note added.")
        else:
            messages.error(request, "Could not save note.")
        return redirect("patients:case_detail", pk=pk)
