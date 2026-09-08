from django.urls import path
from .api import AnnouncementDetail, AnnouncementList

app_name = "staff_announcements_api"
urlpatterns = [
    path("", AnnouncementList.as_view(), name="list"),
    path("<int:pk>/", AnnouncementDetail.as_view(), name="detail"),
]
