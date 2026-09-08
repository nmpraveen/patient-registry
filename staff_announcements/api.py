from rest_framework import generics
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from staff_directory.access import StaffPagination, StaffPermission
from .models import Announcement
from .serializers import AnnouncementSerializer, AnnouncementUpdateSerializer
from .services import announcements_for, save_announcement


@extend_schema_view(get=extend_schema(parameters=[
    OpenApiParameter("manage", bool, description="Settings managers only: include scheduled, expired and inactive records."),
]))
class AnnouncementList(generics.ListCreateAPIView):
    permission_classes = [StaffPermission]
    serializer_class = AnnouncementSerializer
    pagination_class = StaffPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Announcement.objects.none()
        return announcements_for(self.request.user, manage=self.request.query_params.get("manage") == "true")

    def perform_create(self, serializer):
        serializer.instance = save_announcement(self.request.user, serializer.validated_data, request=self.request)


@extend_schema_view(get=extend_schema(parameters=[OpenApiParameter("manage", bool)]))
class AnnouncementDetail(generics.RetrieveUpdateAPIView):
    permission_classes = [StaffPermission]
    serializer_class = AnnouncementSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        return AnnouncementUpdateSerializer if self.request.method == "PATCH" else AnnouncementSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Announcement.objects.none()
        return announcements_for(self.request.user, manage=self.request.query_params.get("manage") == "true")

    def perform_update(self, serializer):
        serializer.instance = save_announcement(self.request.user, serializer.validated_data, pk=self.kwargs["pk"], request=self.request)
