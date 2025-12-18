from django.db import models
from django.conf import settings
from django.utils import timezone
from persons.models import Person
from orders.models import Order
from services.models import Status

# Create your models here.


class Appointment(models.Model):
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_by_%(class)s",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    modified_at = models.DateTimeField(default=timezone.now)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="modified_by_%(class)s",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    person = models.ForeignKey(
        Person, related_name="person_%(class)s", on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    schedule = models.DateTimeField(default=timezone.now)
    with_person = models.ForeignKey(
        Person, related_name="with_person_%(class)s", on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    description = models.CharField(max_length=255, blank=True)
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=2)


    def __str__(self):
        formatted_schedule = self.schedule.strftime("%d.%m.%Y %H:%M")
        return f"{self.person} with {self.with_person} on {formatted_schedule} - {self.description}"
