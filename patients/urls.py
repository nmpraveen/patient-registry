from django.urls import path

from .views import (
    AddCaseNoteView,
    CaseCreateView,
    CaseDetailView,
    CaseListView,
    CaseAutocompleteView,
    CaseUpdateView,
    DashboardView,
    UniversalCaseSearchView,
    AdminSettingsView,
    TaskCreateView,
    TaskUpdateView,
)

app_name = "patients"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("settings/", AdminSettingsView.as_view(), name="settings"),
    path("cases/", CaseListView.as_view(), name="case_list"),
    path("cases/autocomplete/", CaseAutocompleteView.as_view(), name="case_autocomplete"),
    path("cases/universal-search/", UniversalCaseSearchView.as_view(), name="universal_case_search"),
    path("cases/new/", CaseCreateView.as_view(), name="case_create"),
    path("cases/<int:pk>/", CaseDetailView.as_view(), name="case_detail"),
    path("cases/<int:pk>/edit/", CaseUpdateView.as_view(), name="case_edit"),
    path("cases/<int:pk>/tasks/new/", TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/edit/", TaskUpdateView.as_view(), name="task_edit"),
    path("cases/<int:pk>/notes/new/", AddCaseNoteView.as_view(), name="case_note_create"),
]
