from django.urls import path

from .views import PatientCreateView, PatientDetailView, PatientListView, PatientUpdateView

app_name = "patients"

urlpatterns = [
    path("", PatientListView.as_view(), name="list"),
    path("new/", PatientCreateView.as_view(), name="create"),
    path("<int:pk>/", PatientDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", PatientUpdateView.as_view(), name="edit"),
]
