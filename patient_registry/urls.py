from urllib.parse import urlencode

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView

from patients.views import (
    DeviceAuthenticationOptionsView,
    DeviceAuthenticationVerifyView,
    DeviceAwareLoginView,
    DeviceRegistrationOptionsView,
    DeviceRegistrationVerifyView,
    DeviceVerificationView,
)


def admin_login_redirect(request):
    next_url = request.GET.get("next") or "/admin/"
    return redirect(f"{reverse('login')}?{urlencode({'next': next_url})}")

urlpatterns = [
    path("admin/login/", admin_login_redirect, name="admin_login_redirect"),
    path("admin/", admin.site.urls),
    path("login/", DeviceAwareLoginView.as_view(), name="login"),
    path("login/device/", DeviceVerificationView.as_view(), name="login_device_verification"),
    path("login/device/register/options/", DeviceRegistrationOptionsView.as_view(), name="login_device_register_options"),
    path("login/device/register/verify/", DeviceRegistrationVerifyView.as_view(), name="login_device_register_verify"),
    path(
        "login/device/authenticate/options/",
        DeviceAuthenticationOptionsView.as_view(),
        name="login_device_authenticate_options",
    ),
    path(
        "login/device/authenticate/verify/",
        DeviceAuthenticationVerifyView.as_view(),
        name="login_device_authenticate_verify",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/schema/", SpectacularAPIView.as_view(), name="api_schema"),
    path("api/", include("api.urls")),
    path("patients/", include("patients.urls")),
    path("staff/directory/", include("staff_directory.urls")),
    path("staff/announcements/", include("staff_announcements.urls")),
    path("api/staff/directory/", include("staff_directory.api_urls")),
    path("api/staff/announcements/", include("staff_announcements.api_urls")),
    path("staff/reminders/", include("staff_reminders.urls")),
    path("api/staff/reminders/", include("staff_reminders.api_urls")),
    path("", RedirectView.as_view(pattern_name="patients:dashboard", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
