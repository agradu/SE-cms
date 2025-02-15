from django.db import models
from persons.models import Person
from orders.models import OrderElement
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from services.models import DocumentBase, Currency

# Create your models here.


class Invoice(DocumentBase):
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    is_client = models.BooleanField(default=True)
    deadline = models.DateField(default=timezone.now)
    cancellation_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, default=None, related_name="cancellation_to_%(class)s")
    cancelled_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, default=None, related_name="cancelled_from_%(class)s")
    is_recurrent = models.BooleanField(default=False)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"Invoice {self.serial}{self.number} from {formatted_created_at} - {self.person} - {self.description}"

class InvoiceElement(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    element = models.ForeignKey(OrderElement, on_delete=models.CASCADE)

    def __str__(self):
        return f"Invoice element {self.element} from invoice {self.invoice.serial}{self.invoice.number}"

class Proforma(DocumentBase):
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    is_client = models.BooleanField(default=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    deadline = models.DateField(default=timezone.now)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"Proforma {self.serial}{self.number} from {formatted_created_at} - {self.person} - {self.description}"

class ProformaElement(models.Model):
    proforma = models.ForeignKey(Proforma, on_delete=models.CASCADE)
    element = models.ForeignKey(OrderElement, on_delete=models.CASCADE)

    def __str__(self):
        return f"Proforma {self.element} from proforma {self.proforma.serial}{self.proforma.number}"
