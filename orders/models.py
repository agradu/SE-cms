from django.db import models
from persons.models import Person
from services.models import Service, UM, Currency, Status
from django.utils import timezone
from django.conf import settings

# Create your models here.


class Order(models.Model):
    deadline = models.DateTimeField(
        default=timezone.now,
    )
    description = models.CharField(max_length=255, null=True, blank=True)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    is_client = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='created_by_%(class)s', on_delete=models.SET_NULL, null=True, blank=True
    )
    modified_at = models.DateTimeField(default=timezone.now)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='modified_by_%(class)s', on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )

    def __str__(self):
        formatted_deadline = self.deadline.strftime("%d.%m.%Y %H:%M")
        return f"{self.person.firstname} {self.person.lastname} - {formatted_deadline} - {self.description}"


class OrderElement(models.Model):
    service = models.ForeignKey(Service, on_delete=models.SET_DEFAULT, default="")
    description = models.CharField(max_length=255, null=True, blank=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    units = models.SmallIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    um = models.ForeignKey(
        UM, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)

    def __str__(self):
        return f"{self.service.name} - {self.order.person}"
    

class Offer(models.Model):
    deadline = models.DateTimeField(
        default=timezone.now,
    )
    description = models.CharField(max_length=255, null=True, blank=True)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    is_client = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    modified_at = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    to_order = models.ForeignKey(Order, on_delete=models.SET_DEFAULT, null=True, blank=True, default="")

    def __str__(self):
        formatted_deadline = self.deadline.strftime("%d.%m.%Y %H:%M")
        return f"{self.person.firstname} {self.person.lastname} - {formatted_deadline} - {self.description}"


class OfferElement(models.Model):
    service = models.ForeignKey(Service, on_delete=models.SET_DEFAULT, default="")
    description = models.CharField(max_length=255, null=True, blank=True)
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    units = models.SmallIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    um = models.ForeignKey(
        UM, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )

    def __str__(self):
        return f"{self.service.name}"

class TemporaryOrderElement(models.Model):
    service = models.ForeignKey(Service, on_delete=models.SET_DEFAULT, default="")
    description = models.CharField(max_length=255, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    units = models.SmallIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    um = models.ForeignKey(
        UM, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)

    def __str__(self):
        return f"{self.service.name}"