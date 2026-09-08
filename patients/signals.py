from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .audit import current_request, record_audit_event
from .auth_security import bump_auth_version
from .models import (
    AuditEvent,
    CallLog,
    Case,
    CaseActivityLog,
    DeviceApprovalPolicy,
    Patient,
    RoleSetting,
    StaffDeviceCredential,
    StaffDeviceCredentialStatus,
    StaffMobileDeviceCredential,
    Task,
    UserSecurityState,
    VitalEntry,
)


User = get_user_model()
CLINICAL_MODELS = (Patient, Case, Task, VitalEntry, CallLog, CaseActivityLog)
IGNORED_CHANGE_FIELDS = {"created_at", "updated_at", "last_login", "date_joined"}


def _capture_changed_fields(sender, instance):
    if not instance.pk:
        instance._audit_changed_fields = []
        return
    field_names = {
        field.attname: field.name
        for field in sender._meta.concrete_fields
        if not field.primary_key and field.name not in IGNORED_CHANGE_FIELDS
    }
    previous = sender.objects.filter(pk=instance.pk).values(*field_names).first()
    instance._audit_changed_fields = [
        field_names[field_name]
        for field_name in field_names
        if previous is not None and previous.get(field_name) != getattr(instance, field_name)
    ]


def _role_members(*role_names):
    normalized_names = {name for name in role_names if name}
    if not normalized_names:
        return User.objects.none()
    return User.objects.filter(groups__name__in=normalized_names).distinct().order_by("pk")


def _bump_users(users, *, reason, request):
    actor = getattr(request, "user", None)
    for user in users:
        bump_auth_version(user, reason=reason, actor=actor, request=request)


def _device_policy_user_ids(policy):
    if not policy.enabled:
        return set()
    user_ids = set(policy.target_users.values_list("pk", flat=True))
    group_ids = list(policy.target_groups.values_list("pk", flat=True))
    if group_ids:
        user_ids.update(User.objects.filter(groups__pk__in=group_ids).values_list("pk", flat=True))
    return user_ids


def _clinical_ids(instance):
    if isinstance(instance, Patient):
        return instance.pk, None
    if isinstance(instance, Case):
        return instance.patient_id, instance.pk
    case_id = getattr(instance, "case_id", None)
    patient_id = None
    if case_id:
        cached_case = getattr(instance, "case", None)
        patient_id = getattr(cached_case, "patient_id", None)
        if patient_id is None:
            patient_id = Case.objects.filter(pk=case_id).values_list("patient_id", flat=True).first()
    return patient_id, case_id


def _clinical_actor(instance):
    request = current_request()
    request_user = getattr(request, "user", None)
    if getattr(request_user, "is_authenticated", False):
        return request_user
    for attribute in ("updated_by", "created_by", "staff_user", "user"):
        actor = getattr(instance, attribute, None)
        if actor is not None:
            return actor
    return None


@receiver(pre_save)
def capture_audited_model_changes(sender, instance, raw=False, **kwargs):
    if raw or sender not in (
        *CLINICAL_MODELS,
        User,
        Group,
        RoleSetting,
        StaffDeviceCredential,
        StaffMobileDeviceCredential,
        DeviceApprovalPolicy,
    ):
        return
    _capture_changed_fields(sender, instance)
    if sender is RoleSetting and instance.pk:
        instance._previous_role_name = (
            RoleSetting.objects.filter(pk=instance.pk).values_list("role_name", flat=True).first()
        )
    if sender is Group and instance.pk:
        instance._previous_group_name = (
            Group.objects.filter(pk=instance.pk).values_list("name", flat=True).first()
        )
        instance._previous_group_user_ids = set(instance.user_set.values_list("pk", flat=True))
    if sender is StaffDeviceCredential and instance.pk:
        instance._previous_device_status = (
            StaffDeviceCredential.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    if sender is StaffMobileDeviceCredential and instance.pk:
        instance._previous_device_status = (
            StaffMobileDeviceCredential.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    if sender is DeviceApprovalPolicy and instance.pk:
        previous = DeviceApprovalPolicy.objects.filter(pk=instance.pk).first()
        instance._previous_policy_enabled = bool(previous and previous.enabled)
        instance._previous_policy_user_ids = _device_policy_user_ids(previous) if previous else set()


@receiver(post_save)
def audit_model_save(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    changed_fields = list(getattr(instance, "_audit_changed_fields", []))
    request = current_request()

    if sender in CLINICAL_MODELS:
        patient_id, case_id = _clinical_ids(instance)
        record_audit_event(
            category=AuditEvent.Category.CLINICAL,
            action=f"{sender._meta.label_lower}.{'created' if created else 'updated'}",
            actor=_clinical_actor(instance),
            request=request,
            object_type=sender._meta.label_lower,
            object_id=instance.pk,
            patient_id=patient_id,
            case_id=case_id,
            metadata={"changed_fields": changed_fields},
        )
        return

    if sender is User:
        UserSecurityState.objects.get_or_create(user=instance)
        meaningful_fields = [field for field in changed_fields if field not in IGNORED_CHANGE_FIELDS]
        security_fields = sorted(set(meaningful_fields) & {"password", "is_active", "is_superuser"})
        if security_fields:
            bump_auth_version(
                instance,
                reason="user_security_fields_changed",
                actor=getattr(request, "user", None),
                request=request,
            )
        if created or meaningful_fields:
            record_audit_event(
                category=AuditEvent.Category.IAM,
                action=f"user.{'created' if created else 'updated'}",
                request=request,
                object_type="user",
                object_id=instance.pk,
                metadata={"changed_fields": meaningful_fields},
            )
        return

    if sender is RoleSetting:
        if created or changed_fields:
            _bump_users(
                _role_members(getattr(instance, "_previous_role_name", None), instance.role_name),
                reason="role_policy_created" if created else "role_policy_changed",
                request=request,
            )
        record_audit_event(
            category=AuditEvent.Category.IAM,
            action=f"role.{'created' if created else 'updated'}",
            request=request,
            object_type="role_setting",
            object_id=instance.pk,
            metadata={"changed_fields": changed_fields},
        )
        return

    if sender is Group:
        previous_name = getattr(instance, "_previous_group_name", None)
        if not created and previous_name != instance.name:
            _bump_users(
                User.objects.filter(
                    pk__in=getattr(instance, "_previous_group_user_ids", set())
                ).order_by("pk"),
                reason="role_group_identity_changed",
                request=request,
            )
        record_audit_event(
            category=AuditEvent.Category.IAM,
            action=f"role_group.{'created' if created else 'updated'}",
            request=request,
            object_type="auth.group",
            object_id=instance.pk,
            metadata={"changed_fields": changed_fields},
        )
        return

    if sender is StaffDeviceCredential:
        previous_status = getattr(instance, "_previous_device_status", None)
        if (
            not created
            and previous_status != StaffDeviceCredentialStatus.REVOKED
            and instance.status == StaffDeviceCredentialStatus.REVOKED
        ):
            bump_auth_version(
                instance.user,
                reason="device_revoked",
                actor=getattr(request, "user", None),
                request=request,
            )
        record_audit_event(
            category=AuditEvent.Category.IAM,
            action=f"device.{'created' if created else 'updated'}",
            request=request,
            object_type="staff_device_credential",
            object_id=instance.pk,
            metadata={"changed_fields": changed_fields, "status": instance.status},
        )
        return

    if sender is StaffMobileDeviceCredential:
        previous_status = getattr(instance, "_previous_device_status", None)
        if not created and previous_status != instance.status:
            bump_auth_version(
                instance.user,
                reason="mobile_device_status_changed",
                actor=getattr(request, "user", None),
                request=request,
            )
        record_audit_event(
            category=AuditEvent.Category.IAM,
            action=f"mobile_device.{'created' if created else 'updated'}",
            request=request,
            object_type="staff_mobile_device_credential",
            object_id=instance.pk,
            metadata={"changed_fields": changed_fields, "status": instance.status},
        )
        return

    if sender is DeviceApprovalPolicy:
        previous_enabled = getattr(instance, "_previous_policy_enabled", False)
        if previous_enabled != instance.enabled:
            affected_ids = set(getattr(instance, "_previous_policy_user_ids", set()))
            affected_ids.update(_device_policy_user_ids(instance))
            _bump_users(
                User.objects.filter(pk__in=affected_ids).order_by("pk"),
                reason="device_policy_enabled" if instance.enabled else "device_policy_disabled",
                request=request,
            )
        record_audit_event(
            category=AuditEvent.Category.IAM,
            action=f"device_policy.{'created' if created else 'updated'}",
            request=request,
            object_type="device_approval_policy",
            object_id=instance.pk,
            metadata={"changed_fields": changed_fields},
        )


@receiver(pre_delete)
def audit_model_delete(sender, instance, **kwargs):
    if sender in CLINICAL_MODELS:
        patient_id, case_id = _clinical_ids(instance)
        record_audit_event(
            category=AuditEvent.Category.CLINICAL,
            action=f"{sender._meta.label_lower}.deleted",
            actor=_clinical_actor(instance),
            request=current_request(),
            object_type=sender._meta.label_lower,
            object_id=instance.pk,
            patient_id=patient_id,
            case_id=case_id,
        )
        return

    if sender is RoleSetting:
        _bump_users(
            _role_members(instance.role_name),
            reason="role_policy_deleted",
            request=current_request(),
        )

    if sender is Group:
        _bump_users(
            instance.user_set.order_by("pk"),
            reason="role_group_deleted",
            request=current_request(),
        )

    if sender is StaffMobileDeviceCredential:
        bump_auth_version(
            instance.user,
            reason="mobile_device_deleted",
            actor=getattr(current_request(), "user", None),
            request=current_request(),
        )

    if sender is DeviceApprovalPolicy:
        _bump_users(
            User.objects.filter(pk__in=_device_policy_user_ids(instance)).order_by("pk"),
            reason="device_policy_deleted",
            request=current_request(),
        )

    if sender in (User, Group, RoleSetting, StaffDeviceCredential, StaffMobileDeviceCredential, DeviceApprovalPolicy):
        record_audit_event(
            category=AuditEvent.Category.IAM,
            action=f"{sender._meta.label_lower}.deleted",
            request=current_request(),
            object_type=sender._meta.label_lower,
            object_id=instance.pk,
        )


@receiver(m2m_changed, sender=User.groups.through)
def audit_user_group_change(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "pre_clear" and reverse:
        instance._removed_group_user_ids = set(instance.user_set.values_list("pk", flat=True))
        return
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    request = current_request()
    affected_user_ids = pk_set or getattr(instance, "_removed_group_user_ids", set())
    users = User.objects.filter(pk__in=affected_user_ids).order_by("pk") if reverse else [instance]
    for user in users:
        bump_auth_version(
            user,
            reason="user_role_membership_changed",
            actor=getattr(request, "user", None),
            request=request,
        )
    record_audit_event(
        category=AuditEvent.Category.IAM,
        action="user.roles_changed",
        request=request,
        object_type="group" if reverse else "user",
        object_id=instance.pk,
        metadata={
            "operation": action,
            "role_ids": sorted(pk_set or []),
            "reverse": reverse,
        },
    )


def _policy_m2m_affected_users(sender, instance, *, reverse, pk_set):
    if sender is DeviceApprovalPolicy.target_users.through:
        if reverse:
            return {instance.pk}
        if pk_set is None:
            return set(instance.target_users.values_list("pk", flat=True))
        return set(pk_set)
    if reverse:
        return set(instance.user_set.values_list("pk", flat=True))
    group_ids = pk_set
    if group_ids is None:
        group_ids = instance.target_groups.values_list("pk", flat=True)
    return set(User.objects.filter(groups__pk__in=group_ids).values_list("pk", flat=True))


@receiver(m2m_changed, sender=DeviceApprovalPolicy.target_users.through)
@receiver(m2m_changed, sender=DeviceApprovalPolicy.target_groups.through)
def audit_device_policy_target_change(sender, instance, action, reverse, pk_set, **kwargs):
    if action in {"pre_remove", "pre_clear"}:
        affected_ids = _policy_m2m_affected_users(
            sender,
            instance,
            reverse=reverse,
            pk_set=pk_set,
        )
        instance._device_policy_removed_user_ids = affected_ids
        instance._device_policy_removed_was_enabled = (
            DeviceApprovalPolicy.objects.filter(pk__in=pk_set or [], enabled=True).exists()
            if reverse and pk_set is not None
            else (
                instance.device_approval_policies.filter(enabled=True).exists()
                if reverse
                else instance.enabled
            )
        )
        return
    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    if action == "post_add":
        affected_ids = _policy_m2m_affected_users(
            sender,
            instance,
            reverse=reverse,
            pk_set=pk_set,
        )
    else:
        affected_ids = set(getattr(instance, "_device_policy_removed_user_ids", set()))
    policy_enabled = (
        (
            DeviceApprovalPolicy.objects.filter(pk__in=pk_set or [], enabled=True).exists()
            if reverse
            else instance.enabled
        )
        if action == "post_add"
        else getattr(instance, "_device_policy_removed_was_enabled", False)
    )
    if policy_enabled:
        _bump_users(
            User.objects.filter(pk__in=affected_ids).order_by("pk"),
            reason="device_policy_targets_changed",
            request=current_request(),
        )
    record_audit_event(
        category=AuditEvent.Category.IAM,
        action="device_policy.targets_changed",
        request=current_request(),
        object_type="device_approval_policy",
        object_id="multiple" if reverse else instance.pk,
        metadata={"operation": action, "target_kind": "user" if sender is DeviceApprovalPolicy.target_users.through else "group"},
    )
