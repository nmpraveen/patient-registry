from django.urls import path
from . import views

app_name = "staff_announcements"
urlpatterns = [
    path("", views.announcement_list, name="list"),
    path("banner/", views.announcement_banner, name="banner"),
    path("new/", views.announcement_edit, name="create"),
    path("<int:pk>/", views.announcement_detail, name="detail"),
    path("<int:pk>/edit/", views.announcement_edit, name="edit"),
]
