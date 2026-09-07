"""Explicit ANC actions shared by HTML and mobile writes."""
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .follow_up import OPEN_STATUSES
from .models import CaseStatus, TaskStatus, is_anc_case
from .anc_validation import validate_anc_outcome


class AncActionForm(forms.Form):
    action = forms.ChoiceField(choices=[("outcome", "Record outcome"), ("correct_edd", "Correct USG EDD")])
    base_updated_at = forms.DateTimeField(widget=forms.HiddenInput)
    reason = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))
    outcome = forms.ChoiceField(required=False, choices=[("", "Choose outcome"), ("delivery", "Delivery"),
        ("loss_to_follow_up", "Loss to follow-up"), ("referral", "Referral"), ("other", "Other resolution")])
    outcome_date = forms.DateField(label="Outcome / delivery / referral date", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    referral_destination = forms.CharField(required=False, max_length=255)
    continue_follow_up = forms.ChoiceField(label="Follow-up after outcome", required=False, choices=[("", "Choose follow-up"),
        ("continue", "Continue follow-up"), ("close", "Close this case")])
    usg_edd = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    task_policy = forms.ChoiceField(choices=[("retain", "Retain all task dates and statuses"),
        ("cancel_selected", "Cancel selected open tasks")])
    cancel_task_ids = forms.MultipleChoiceField(label="Open tasks to cancel", required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, case, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxSelectMultiple, forms.HiddenInput)):
                field.widget.attrs["class"] = "form-control"
        self.fields["cancel_task_ids"].choices = [(str(t.pk), f"{t.title} — {t.due_date} — {t.get_status_display()}")
            for t in case.tasks.filter(status__in=OPEN_STATUSES).order_by("due_date", "pk")]

    def clean(self):
        data = super().clean()
        if data.get("action") == "outcome":
            for field in ("outcome", "outcome_date", "continue_follow_up"):
                if not data.get(field):
                    self.add_error(field, "Required for an outcome.")
            try:
                validate_anc_outcome(outcome=data.get("outcome"), outcome_date=data.get("outcome_date"),
                    reason=data.get("reason"), destination=data.get("referral_destination"),
                    continue_follow_up=(data["continue_follow_up"] == "continue") if data.get("continue_follow_up") else None)
            except ValidationError as error:
                fields = {"anc_outcome": "outcome", "anc_outcome_date": "outcome_date",
                    "anc_outcome_reason": "reason", "anc_referral_destination": "referral_destination",
                    "anc_continue_follow_up": "continue_follow_up"}
                for field, errors in error.message_dict.items():
                    self.add_error(fields[field], errors)
        elif data.get("action") == "correct_edd":
            if not data.get("usg_edd"):
                self.add_error("usg_edd", "Enter the corrected USG EDD.")
            if data.get("task_policy") != "retain":
                self.add_error("task_policy", "EDD correction retains all existing tasks.")
        if data.get("cancel_task_ids") and data.get("task_policy") != "cancel_selected":
            self.add_error("cancel_task_ids", "Choose the cancel-selected policy to cancel tasks.")
        return data


@transaction.atomic
def apply_anc_action(*, case, user, data):
    # Imported here to avoid the existing views/forms import cycle.
    from .views import has_capability, can_transition_grey_tasks, create_case_activity
    if not has_capability(user, "case_edit", fresh=True):
        raise PermissionDenied("You do not have permission to edit cases.")
    if not is_anc_case(case):
        raise ValidationError("This action is only available for ANC cases.")
    if case.updated_at != data["base_updated_at"]:
        raise ValidationError("This case changed. Reload before recording the action.")
    noncompleted_tasks = list(case.tasks.select_for_update().exclude(status=TaskStatus.COMPLETED))
    tasks = [task for task in noncompleted_tasks if task.status in OPEN_STATUSES]
    selected = set(map(int, data.get("cancel_task_ids", [])))
    if not selected.issubset({t.pk for t in tasks}):
        raise ValidationError("Selected tasks changed. Reload before recording the action.")
    if selected and not has_capability(user, "task_edit", fresh=True):
        raise PermissionDenied("Task edit permission is required to cancel tasks.")
    if data["action"] == "correct_edd":
        note = f"USG EDD corrected: {case.usg_edd or 'missing'} -> {data['usg_edd']}. Effective EDD before: {case.effective_edd or 'missing'}. Existing tasks retained."
        case.usg_edd = data["usg_edd"]
    else:
        continuing = data["continue_follow_up"] == "continue"
        new_status = CaseStatus.ACTIVE if continuing else (
            CaseStatus.LOSS_TO_FOLLOW_UP if data["outcome"] == "loss_to_follow_up" else CaseStatus.COMPLETED)
        if new_status in (CaseStatus.ACTIVE, CaseStatus.LOSS_TO_FOLLOW_UP) and any(
            (timezone.localdate() - t.due_date).days > 30 for t in noncompleted_tasks
        ) and not can_transition_grey_tasks(user, fresh=True):
            raise PermissionDenied("Your role does not allow this Grey List status transition.")
        note = f"ANC outcome: {case.anc_outcome or 'unrecorded'} -> {data['outcome']} on {data['outcome_date']}. Destination: {data.get('referral_destination') or 'none'}. Follow-up: {data['continue_follow_up']}. Case status: {case.status} -> {new_status}. Task policy: {data['task_policy']}."
        case.anc_outcome = data["outcome"]
        case.anc_outcome_date = data["outcome_date"]
        case.anc_outcome_reason = data["reason"]
        case.anc_referral_destination = data.get("referral_destination", "")
        case.anc_continue_follow_up = continuing
        case.status = new_status
    case.save()
    for task in tasks:
        if task.pk in selected:
            task.status = TaskStatus.CANCELLED
            task.save(update_fields=["status", "updated_at"])
            create_case_activity(case=case, user=user, task=task, note="Task explicitly cancelled with ANC outcome.")
    create_case_activity(case=case, user=user, note=f"{note} Reason: {data['reason']}")
    return case
