from django.db import models
from persons.models import Person
from orders.models import OrderElement
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from services.models import Currency

# Create your models here.


class Invoice(models.Model):
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
    serial = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=20, blank=True)
    deadline = models.DateField(default=timezone.now)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    description = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"Invoice {self.serial}{self.number} from {formatted_created_at} - {self.person} - {self.description}"


class InvoiceElement(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    element = models.ForeignKey(OrderElement, on_delete=models.CASCADE)

    def __str__(self):
        return f"Invoice element {self.element} from invoice {self.invoice.serial}{self.invoice.number}"

class Proforma(models.Model):
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
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    serial = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=20, blank=True)
    deadline = models.DateField(default=timezone.now)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    description = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"Proforma {self.serial}{self.number} from {formatted_created_at} - {self.person} - {self.description}"


class ProformaElement(models.Model):
    proforma = models.ForeignKey(Proforma, on_delete=models.CASCADE)
    element = models.ForeignKey(OrderElement, on_delete=models.CASCADE)

    def __str__(self):
        return f"Proforma {self.element} from proforma {self.proforma.serial}{self.proforma.number}"
