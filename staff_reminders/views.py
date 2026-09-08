from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from rest_framework.exceptions import ValidationError as APIValidationError

from .api import occurrence_rows
from .forms import ReminderForm
from .serializers import CompleteSerializer
from .policy import require_staff, visible_reminders
from .services import StaleReminder, complete_occurrence, create_reminder, hospital_today, update_reminder


@login_required
def reminder_list(request):
    require_staff(request.user)
    status = request.GET.get("status", "notices")
    if status not in ("notices", "pending", "completed", "all"):
        status = "notices"
    occurrences = occurrence_rows(request.user, {"status": status})
    page = Paginator(occurrences, 50).get_page(request.GET.get("page"))
    return render(request, "staff_reminders/list.html", {"page_obj": page, "status": status, "today": hospital_today()})


@login_required
def reminder_detail(request, pk):
    reminder = get_object_or_404(visible_reminders(request.user).select_related("assignee", "owner"), pk=pk)
    page = Paginator(reminder.occurrences.select_related("completed_by"), 50).get_page(request.GET.get("page"))
    return render(request, "staff_reminders/detail.html", {"reminder": reminder, "page_obj": page})


@login_required
def reminder_edit(request, pk=None):
    require_staff(request.user)
    reminder = get_object_or_404(visible_reminders(request.user), pk=pk) if pk else None
    form = ReminderForm(request.POST if request.method == "POST" else None, reminder=reminder)
    status = 200
    if request.method == "POST" and form.is_valid():
        try:
            if reminder:
                reminder = update_reminder(request.user, reminder.pk, form.values(), form.cleaned_data["version"], request=request)
            else:
                reminder = create_reminder(request.user, form.values(), request=request)
            return redirect("staff_reminders:detail", pk=reminder.pk)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
            status = 409 if isinstance(exc, StaleReminder) else 400
    return render(request, "staff_reminders/form.html", {"form": form, "reminder": reminder}, status=status)


@login_required
@require_POST
def occurrence_complete(request, pk):
    try:
        payload = CompleteSerializer(data={"version": request.POST.get("version")})
        payload.is_valid(raise_exception=True)
        occurrence = complete_occurrence(request.user, pk, payload.validated_data["version"], request=request)
    except (ValidationError, APIValidationError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        return redirect("staff_reminders:list")
    messages.success(request, "Reminder completed.")
    return redirect("staff_reminders:detail", pk=occurrence.reminder_id)
