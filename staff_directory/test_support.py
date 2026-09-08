from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from patients.auth_security import AUTH_VERSION_SESSION_KEY, current_auth_version
from patients.models import CaseDataScope, RoleSetting


def staff_user(name, *, manager=False):
    role, _ = RoleSetting.objects.get_or_create(
        role_name="Operations manager" if manager else "Operations reader",
        defaults={"can_manage_settings": manager, "case_data_scope": CaseDataScope.NONE},
    )
    group, _ = Group.objects.get_or_create(name=role.role_name)
    user = get_user_model().objects.create_user(username=name, password="synthetic-test-password")
    user.groups.add(group)
    return user


def web_login(client, user):
    client.force_login(user)
    session = client.session
    session[AUTH_VERSION_SESSION_KEY] = current_auth_version(user)
    session.save()
