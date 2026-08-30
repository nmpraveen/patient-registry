from django.db.models import Q

from .models import Case, CaseDataScope, Patient
from .policy import effective_role_policy


def _current_intake_policy(actor):
    policy = effective_role_policy(actor, fresh=True)
    allowed = "case_create" in policy.capabilities and policy.can_intake_patient_lookup
    return allowed, policy.case_data_scope


def case_intake_patient_queryset(*, actor, queryset=None):
    """Return patients that the current actor may select for new-case intake.

    The policy is read fresh from the database on every call so a form cannot
    keep using a cached role after an administrator revokes its scope.
    """

    queryset = queryset if queryset is not None else Patient.objects.all()
    queryset = queryset.filter(merged_into__isnull=True)
    allowed, scope = _current_intake_policy(actor)
    if not allowed or scope == CaseDataScope.NONE:
        return queryset.none()
    if scope == CaseDataScope.ALL:
        return queryset
    return queryset.filter(
        Q(created_by=actor)
        | Q(cases__is_archived=False, cases__created_by=actor)
        | Q(cases__is_archived=False, cases__tasks__assigned_user=actor)
    ).distinct()


def resolve_case_intake_patient(*, actor, patient_id, lock=False):
    """Resolve one selection without revealing whether a denied patient exists."""

    allowed, scope = _current_intake_policy(actor)
    if not allowed or scope == CaseDataScope.NONE or not patient_id:
        return None
    queryset = Patient.objects.filter(pk=patient_id, merged_into__isnull=True)
    if lock:
        queryset = queryset.select_for_update()
    patient = queryset.first()
    if patient is None or scope == CaseDataScope.ALL:
        return patient
    assigned = patient.created_by_id == actor.pk or Case.objects.filter(
        patient_id=patient.pk,
        is_archived=False,
    ).filter(Q(created_by=actor) | Q(tasks__assigned_user=actor)).exists()
    return patient if assigned else None
