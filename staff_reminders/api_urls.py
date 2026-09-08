from django.urls import path
from . import api

app_name = "staff_reminders_api"
urlpatterns = [
    path("", api.ReminderList.as_view(), name="list"),
    path("assignees/", api.AssigneeList.as_view(), name="assignees"),
    path("occurrences/", api.OccurrenceList.as_view(), name="occurrences"),
    path("occurrences/<int:pk>/complete/", api.OccurrenceComplete.as_view(), name="complete"),
    path("<int:pk>/", api.ReminderDetail.as_view(), name="detail"),
]
