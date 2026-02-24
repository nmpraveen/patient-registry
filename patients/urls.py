from django.urls import path

from .views import (
    AddCaseNoteView,
    CaseCreateView,
    CaseDetailView,
    CaseListView,
    CaseUpdateView,
    DashboardView,
    TaskCreateView,
    TaskUpdateView,
)

app_name = "patients"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("cases/", CaseListView.as_view(), name="case_list"),
    path("cases/new/", CaseCreateView.as_view(), name="case_create"),
    path("cases/<int:pk>/", CaseDetailView.as_view(), name="case_detail"),
    path("cases/<int:pk>/edit/", CaseUpdateView.as_view(), name="case_edit"),
    path("cases/<int:pk>/tasks/new/", TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/edit/", TaskUpdateView.as_view(), name="task_edit"),
    path("cases/<int:pk>/notes/new/", AddCaseNoteView.as_view(), name="case_note_create"),
]
