from staff_directory.access import is_authorized_staff
from django.utils import timezone
from .services import banner_for


def staff_operations(request):
    if not is_authorized_staff(request.user):
        return {}
    return {"staff_operations_allowed": True, "staff_announcement_banner": banner_for(request.user), "server_now": timezone.now()}
