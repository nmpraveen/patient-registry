from django.urls import path
from . import views

app_name = "staff_directory"
urlpatterns = [
    path("", views.contact_list, name="list"),
    path("new/", views.contact_edit, name="create"),
    path("<int:pk>/", views.contact_detail, name="detail"),
    path("<int:pk>/edit/", views.contact_edit, name="edit"),
    path("<int:pk>/favourite/", views.contact_favourite, name="favourite"),
]
