from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.response import Response

from .access import StaffPagination, StaffPermission
from .models import Contact
from .serializers import ContactSerializer, ContactUpdateSerializer, FavouriteSerializer
from .services import contacts_for, save_contact, set_favourite


@extend_schema_view(get=extend_schema(parameters=[
    OpenApiParameter("q", str, description="Search name, specialty, organisation and phones; max 100 characters."),
    OpenApiParameter("favourites", bool),
    OpenApiParameter("include_inactive", bool, description="Settings managers only."),
]))
class ContactList(generics.ListCreateAPIView):
    permission_classes = [StaffPermission]
    serializer_class = ContactSerializer
    pagination_class = StaffPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Contact.objects.none()
        return contacts_for(self.request.user,
                            include_inactive=self.request.query_params.get("include_inactive") == "true",
                            q=self.request.query_params.get("q", ""),
                            favourites=self.request.query_params.get("favourites") == "true")

    def perform_create(self, serializer):
        serializer.instance = save_contact(self.request.user, serializer.validated_data, request=self.request)


@extend_schema_view(get=extend_schema(parameters=[OpenApiParameter("include_inactive", bool)]))
class ContactDetail(generics.RetrieveUpdateAPIView):
    permission_classes = [StaffPermission]
    serializer_class = ContactSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        return ContactUpdateSerializer if self.request.method == "PATCH" else ContactSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Contact.objects.none()
        return contacts_for(self.request.user,
                            include_inactive=self.request.query_params.get("include_inactive") == "true")

    def perform_update(self, serializer):
        serializer.instance = save_contact(self.request.user, serializer.validated_data, pk=self.kwargs["pk"], request=self.request)


class ContactFavourite(generics.GenericAPIView):
    permission_classes = [StaffPermission]
    serializer_class = FavouriteSerializer

    @extend_schema(responses=ContactSerializer)
    def put(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = set_favourite(request.user, pk, serializer.validated_data["is_favourite"], request=request)
        return Response(ContactSerializer(contact, context={"request": request}).data)
