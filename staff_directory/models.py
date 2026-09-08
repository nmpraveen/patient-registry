from django.conf import settings
from django.db import models


class Contact(models.Model):
    name = models.CharField(max_length=160)
    role_specialty = models.CharField(max_length=160, blank=True)
    organization = models.CharField(max_length=160, blank=True)
    phones = models.JSONField(default=list)
    notes = models.TextField(blank=True, max_length=2000)
    is_active = models.BooleanField(default=True, db_index=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return self.name


class Favourite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="favourites")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "contact"), name="staff_directory_unique_favourite")
        ]
