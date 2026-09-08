from django.urls import path
from . import views

app_name = "staff_reminders"
urlpatterns = [
    path("", views.reminder_list, name="list"),
    path("new/", views.reminder_edit, name="create"),
    path("<int:pk>/", views.reminder_detail, name="detail"),
    path("<int:pk>/edit/", views.reminder_edit, name="edit"),
    path("occurrences/<int:pk>/complete/", views.occurrence_complete, name="complete"),
]
