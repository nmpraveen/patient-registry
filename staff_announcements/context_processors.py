from staff_directory.access import is_authorized_staff


def staff_operations(request):
    if not is_authorized_staff(request.user):
        return {}
    return {"staff_operations_allowed": True}
