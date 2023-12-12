from django.db import models
from persons.models import Person
from services.models import Service, UM, Currency, Status
from django.utils import timezone
from django.conf import settings

# Create your models here.


class Order(models.Model):
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
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    is_client = models.BooleanField(default=True)
    deadline = models.DateTimeField(
        default=timezone.now,
    )
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)
    serial = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=20, blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    description = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        formatted_deadline = self.deadline.strftime("%d.%m.%Y %H:%M")
        return f"Order - {self.person} - {formatted_deadline} - {self.description} ({self.value}{self.currency.symbol})"


class OrderElement(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.SET_DEFAULT, default="")
    description = models.CharField(max_length=255, null=True, blank=True)
    quantity = models.SmallIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    um = models.ForeignKey(
        UM, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)

    def __str__(self):
        return f"Elm. #{self.order.id} - {self.service.name} ({self.price}{self.order.currency.symbol} * {self.quantity})"


class Offer(models.Model):
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
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    deadline = models.DateTimeField(
        default=timezone.now,
    )
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)
    serial = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=20, blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    description = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        formatted_deadline = self.deadline.strftime("%d.%m.%Y %H:%M")
        return f"Offer - {self.person} - {formatted_deadline} - {self.description} ({self.value}{self.currency.symbol})"


class OfferElement(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.SET_DEFAULT, default="")
    description = models.CharField(max_length=255, null=True, blank=True)
    quantity = models.SmallIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    um = models.ForeignKey(
        UM, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )

    def __str__(self):
        return f"OferElm. #{self.offer.id} - {self.service.name} ({self.price}{self.offer.currency.symbol} * {self.quantity})"

