from django.urls import path
from .api import ContactDetail, ContactFavourite, ContactList

app_name = "staff_directory_api"
urlpatterns = [
    path("", ContactList.as_view(), name="list"),
    path("<int:pk>/", ContactDetail.as_view(), name="detail"),
    path("<int:pk>/favourite/", ContactFavourite.as_view(), name="favourite"),
]
