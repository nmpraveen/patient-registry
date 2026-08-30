from dataclasses import dataclass

from .models import CaseDataScope, RoleSetting


CAPABILITY_FIELD_MAP = {
    "case_create": "can_case_create",
    "case_edit": "can_case_edit",
    "task_create": "can_task_create",
    "task_edit": "can_task_edit",
    "task_reopen": "can_task_reopen",
    "note_add": "can_note_add",
    "patient_merge": "can_patient_merge",
    "manage_settings": "can_manage_settings",
}


@dataclass(frozen=True)
class EffectiveRolePolicy:
    case_data_scope: str
    can_access_call_queue: bool
    can_intake_patient_lookup: bool
    capabilities: frozenset[str]
    role_names: frozenset[str]


DENY_ALL_POLICY = EffectiveRolePolicy(
    case_data_scope=CaseDataScope.NONE,
    can_access_call_queue=False,
    can_intake_patient_lookup=False,
    capabilities=frozenset(),
    role_names=frozenset(),
)


def effective_role_policy(user, *, fresh=False):
    """Resolve the deterministic union of explicit policies for current groups.

    Case scope uses NONE < ASSIGNED < ALL. Boolean capabilities are an OR
    across matching roles. Role names themselves never grant access.
    """

    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return DENY_ALL_POLICY
    if getattr(user, "is_superuser", False):
        return EffectiveRolePolicy(
            case_data_scope=CaseDataScope.ALL,
            can_access_call_queue=True,
            can_intake_patient_lookup=True,
            capabilities=frozenset(CAPABILITY_FIELD_MAP),
            role_names=frozenset(),
        )

    cache_name = "_medtrack_effective_role_policy"
    if not fresh:
        cached = getattr(user, cache_name, None)
        if cached is not None:
            return cached

    rows = list(
        RoleSetting.objects.filter(
            role_name__in=user.groups.values_list("name", flat=True),
        ).values(
            "role_name",
            "case_data_scope",
            "can_access_call_queue",
            "can_intake_patient_lookup",
            *CAPABILITY_FIELD_MAP.values(),
        )
    )
    scopes = {row["case_data_scope"] for row in rows}
    if CaseDataScope.ALL in scopes:
        scope = CaseDataScope.ALL
    elif CaseDataScope.ASSIGNED in scopes:
        scope = CaseDataScope.ASSIGNED
    else:
        scope = CaseDataScope.NONE
    policy = EffectiveRolePolicy(
        case_data_scope=scope,
        can_access_call_queue=any(row["can_access_call_queue"] for row in rows),
        can_intake_patient_lookup=any(row["can_intake_patient_lookup"] for row in rows),
        capabilities=frozenset(
            capability
            for capability, field_name in CAPABILITY_FIELD_MAP.items()
            if any(row[field_name] for row in rows)
        ),
        role_names=frozenset(row["role_name"] for row in rows),
    )
    if not fresh:
        setattr(user, cache_name, policy)
    return policy


def has_capability(user, capability, *, fresh=False):
    return capability in effective_role_policy(user, fresh=fresh).capabilities


def case_data_scope(user, *, fresh=False):
    return effective_role_policy(user, fresh=fresh).case_data_scope


def has_call_queue_scope(user, *, fresh=False):
    return effective_role_policy(user, fresh=fresh).can_access_call_queue


def has_intake_lookup_scope(user, *, fresh=False):
    return effective_role_policy(user, fresh=fresh).can_intake_patient_lookup


def has_all_case_scope(user, *, fresh=False):
    return case_data_scope(user, fresh=fresh) == CaseDataScope.ALL


def role_data_scope_payload(user, *, fresh=False):
    policy = effective_role_policy(user, fresh=fresh)
    return {
        "case_data_scope": policy.case_data_scope,
        "call_queue": policy.can_access_call_queue,
        "intake_patient_lookup": policy.can_intake_patient_lookup,
    }


def can_access_case_data(user, *, fresh=False):
    policy = effective_role_policy(user, fresh=fresh)
    return policy.case_data_scope != CaseDataScope.NONE or policy.can_access_call_queue


def can_transition_grey_tasks(user, *, fresh=False):
    return has_capability(user, "task_reopen", fresh=fresh)
