from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404

from .access import audit_change, mutation_actor, require_staff, StaleVersion
from .models import Contact, Favourite


def contacts_for(user, *, include_inactive=False, q="", favourites=False):
    require_staff(user)
    queryset = Contact.objects.all()
    if include_inactive:
        require_staff(user, manage=True)
    else:
        queryset = queryset.filter(is_active=True)
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q[:100]) | Q(role_specialty__icontains=q[:100])
            | Q(organization__icontains=q[:100]) | Q(phones__icontains=q[:100])
        )
    queryset = queryset.annotate(favourite_for_user=Exists(
        Favourite.objects.filter(contact_id=OuterRef("pk"), user=user)))
    if favourites:
        queryset = queryset.filter(favourite_for_user=True)
    return queryset


@transaction.atomic
def save_contact(user, data, *, pk=None, request=None):
    actor = mutation_actor(user, manage=True, request=request)
    data = dict(data)
    expected = data.pop("version", None)
    if pk is None:
        contact = Contact()
    else:
        contact = get_object_or_404(Contact.objects.select_for_update(), pk=pk)
        if expected != contact.version:
            raise StaleVersion()
        contact.version += 1
    for field, value in data.items():
        setattr(contact, field, value)
    contact.full_clean()
    contact.save()
    audit_change(actor, contact, "staff_directory.created" if pk is None else "staff_directory.updated", data)
    return contact


@transaction.atomic
def set_favourite(user, pk, desired, *, request=None):
    actor = mutation_actor(user, request=request)
    contact = get_object_or_404(Contact.objects.select_for_update(), pk=pk, is_active=True)
    if desired:
        _, changed = Favourite.objects.get_or_create(user=actor, contact=contact)
    else:
        changed, _ = Favourite.objects.filter(user=actor, contact=contact).delete()
    if changed:
        audit_change(actor, contact, "staff_directory.favourite_set", ("is_favourite",))
    return contact
