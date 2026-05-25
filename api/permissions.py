from rest_framework import permissions

from patients.views import can_access_case_data


class HasMobileCaseAccess(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and can_access_case_data(request.user))
