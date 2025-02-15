from django.db import models
from persons.models import Person
from services.models import DocumentBase, DocumentElement, Service, UM, Currency, Status
from django.utils import timezone
from django.conf import settings

# Create your models here.


class Order(DocumentBase):
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    is_client = models.BooleanField(default=True)
    deadline = models.DateTimeField(default=timezone.now)
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)

    def __str__(self):
        formatted_deadline = self.deadline.strftime("%d.%m.%Y %H:%M")
        return f"Order {self.serial}{self.number} - {self.person} - {formatted_deadline} - {self.description} ({self.value}{self.currency.symbol})"

class OrderElement(DocumentElement):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)

    def __str__(self):
        return f"Elm. #{self.order.id} - {self.service.name} ({self.price}{self.order.currency.symbol} * {self.quantity})"


class Offer(DocumentBase):
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    deadline = models.DateTimeField(default=timezone.now)
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)

    def __str__(self):
        formatted_deadline = self.deadline.strftime("%d.%m.%Y %H:%M")
        return f"Offer {self.serial}{self.number} - {self.person} - {formatted_deadline} - {self.description} ({self.value}{self.currency.symbol})"

class OfferElement(DocumentElement):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)

    def __str__(self):
        return f"OferElm. #{self.offer.id} - {self.service.name} ({self.price}{self.offer.currency.symbol} * {self.quantity})"