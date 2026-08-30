from django.contrib.auth import get_user_model
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
    field_names = [
        field.attname
        for field in sender._meta.concrete_fields
        if not field.primary_key and field.name not in IGNORED_CHANGE_FIELDS
    ]
    previous = sender.objects.filter(pk=instance.pk).values(*field_names).first()
    instance._audit_changed_fields = [
        sender._meta.get_field(field_name.removesuffix("_id")).name
        if field_name.endswith("_id")
        else field_name
        for field_name in field_names
        if previous is not None and previous.get(field_name) != getattr(instance, field_name)
    ]


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
    if raw or sender not in (*CLINICAL_MODELS, User, RoleSetting, StaffDeviceCredential, DeviceApprovalPolicy):
        return
    _capture_changed_fields(sender, instance)
    if sender is StaffDeviceCredential and instance.pk:
        instance._previous_device_status = (
            StaffDeviceCredential.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )


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
        if not created and changed_fields:
            for user in User.objects.filter(groups__name=instance.role_name).distinct():
                bump_auth_version(
                    user,
                    reason="role_policy_changed",
                    actor=getattr(request, "user", None),
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

    if sender is DeviceApprovalPolicy:
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

    if sender in (User, RoleSetting, StaffDeviceCredential, DeviceApprovalPolicy):
        record_audit_event(
            category=AuditEvent.Category.IAM,
            action=f"{sender._meta.label_lower}.deleted",
            request=current_request(),
            object_type=sender._meta.label_lower,
            object_id=instance.pk,
        )


@receiver(m2m_changed, sender=User.groups.through)
def audit_user_group_change(sender, instance, action, reverse, pk_set, **kwargs):
    if reverse or action not in {"post_add", "post_remove", "post_clear"}:
        return
    request = current_request()
    is_initial_assignment = False
    if action == "post_add" and instance.last_login is None:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

        is_initial_assignment = not OutstandingToken.objects.filter(user=instance).exists()
    if not is_initial_assignment:
        bump_auth_version(
            instance,
            reason="user_role_membership_changed",
            actor=getattr(request, "user", None),
            request=request,
        )
    record_audit_event(
        category=AuditEvent.Category.IAM,
        action="user.roles_changed",
        request=request,
        object_type="user",
        object_id=instance.pk,
        metadata={
            "operation": action,
            "role_ids": sorted(pk_set or []),
            "initial_assignment": is_initial_assignment,
        },
    )
