"""Case attention predicates. Callers must apply their access scope first."""
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Case, CaseStatus, Task, TaskStatus

OPEN_STATUSES = (TaskStatus.SCHEDULED, TaskStatus.AWAITING_REPORTS)


def attention_queryset(queryset, today=None):
    today = today or timezone.localdate()
    open_tasks = Task.objects.filter(case_id=OuterRef("pk"), status__in=OPEN_STATUSES)
    return queryset.annotate(
        attention_edd=Coalesce("usg_edd", "edd"),
        attention_open=Exists(open_tasks),
        attention_task_overdue=Exists(open_tasks.filter(due_date__lt=today)),
    )


def edd_overdue_query(today=None):
    return Q(category__name__iexact="ANC", anc_outcome="", attention_edd__isnull=False,
             attention_edd__lt=today or timezone.localdate())


def attention_filter(queryset, bucket, today=None):
    queryset = attention_queryset(queryset, today).filter(status=CaseStatus.ACTIVE, is_archived=False)
    if bucket == "overdue":
        return queryset.filter(edd_overdue_query(today) | Q(attention_task_overdue=True))
    if bucket == "dormant":
        return queryset.filter(attention_open=False).exclude(edd_overdue_query(today))
    if bucket == "edd_missing":
        return queryset.filter(category__name__iexact="ANC", anc_outcome="", attention_edd__isnull=True)
    return queryset


def follow_up_payload(case):
    if not hasattr(case, "attention_open"):
        case = attention_queryset(Case.objects.select_related("category")).get(pk=case.pk)
    active = case.status == CaseStatus.ACTIVE and not case.is_archived
    unresolved_anc = case.category.name.lower() == "anc" and not case.anc_outcome
    edd_overdue = bool(active and unresolved_anc and case.attention_edd and case.attention_edd < timezone.localdate())
    missing = bool(active and unresolved_anc and not case.attention_edd)
    dormant = bool(active and not case.attention_open and not edd_overdue)
    label = "Overdue — EDD" if edd_overdue else (
        "Overdue" if active and case.attention_task_overdue else "Dormant" if dormant else case.get_status_display()
    )
    return {"label": label, "dormant": dormant, "edd_overdue": edd_overdue,
            "edd_missing": missing, "effective_edd": case.effective_edd,
            "outcome": case.anc_outcome, "outcome_label": case.get_anc_outcome_display(),
            "outcome_date": case.anc_outcome_date, "reason": case.anc_outcome_reason,
            "referral_destination": case.anc_referral_destination,
            "continue_follow_up": case.anc_continue_follow_up}
