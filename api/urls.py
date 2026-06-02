from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    CallOutcomeView,
    CaseDetailView,
    CaseEditFormView,
    CaseFormMetadataView,
    CaseListView,
    CaseVitalsView,
    CategoryMetadataView,
    DeviceTokenView,
    LogoutView,
    MeView,
    NotificationReadView,
    NotificationsView,
    PatientSearchView,
    TaskCompleteView,
    TaskCreateView,
    TaskDetailView,
    TaskFormMetadataView,
    TaskNoteView,
    VitalsDetailView,
    VitalsThresholdsView,
)

app_name = "api"

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("cases/", CaseListView.as_view(), name="case_list"),
    path("patients/", PatientSearchView.as_view(), name="patient_search"),
    path("cases/<int:pk>/", CaseDetailView.as_view(), name="case_detail"),
    path("cases/<int:pk>/edit-form/", CaseEditFormView.as_view(), name="case_edit_form"),
    path("cases/<int:pk>/call-outcome/", CallOutcomeView.as_view(), name="case_call_outcome"),
    path("cases/<int:pk>/vitals/", CaseVitalsView.as_view(), name="case_vitals"),
    path("cases/<int:pk>/tasks/", TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/", TaskDetailView.as_view(), name="task_detail"),
    path("tasks/<int:pk>/complete/", TaskCompleteView.as_view(), name="task_complete"),
    path("tasks/<int:pk>/note/", TaskNoteView.as_view(), name="task_note"),
    path("vitals/<int:pk>/", VitalsDetailView.as_view(), name="vitals_detail"),
    path("vitals-thresholds/", VitalsThresholdsView.as_view(), name="vitals_thresholds"),
    path("devices/", DeviceTokenView.as_view(), name="devices"),
    path("notifications/", NotificationsView.as_view(), name="notifications"),
    path("notifications/<int:pk>/read/", NotificationReadView.as_view(), name="notification_read"),
    path("metadata/categories/", CategoryMetadataView.as_view(), name="category_metadata"),
    path("metadata/case-form/", CaseFormMetadataView.as_view(), name="case_form_metadata"),
    path("metadata/task-form/", TaskFormMetadataView.as_view(), name="task_form_metadata"),
]
