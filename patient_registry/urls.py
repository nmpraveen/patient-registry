from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.views.generic import RedirectView

from patients.views import (
    DeviceAuthenticationOptionsView,
    DeviceAuthenticationVerifyView,
    DeviceAwareLoginView,
    DeviceRegistrationOptionsView,
    DeviceRegistrationVerifyView,
    DeviceVerificationView,
)

urlpatterns = [
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
    path("patients/", include("patients.urls")),
    path("", RedirectView.as_view(pattern_name="patients:dashboard", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
