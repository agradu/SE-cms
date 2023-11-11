from django.db import models
from persons.models import Person
from invoices.models import Invoice
from receipts.models import Receipt
from services.models import Currency
from django.conf import settings
from django.utils import timezone

# Create your models here.


class Payment(models.Model):
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    receipt = models.ForeignKey(
        Receipt, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    description = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='created_by_%(class)s', on_delete=models.SET_NULL, null=True, blank=True
    )
    modified_at = models.DateTimeField(default=timezone.now)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='modified_by_%(class)s', on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"{formatted_created_at} - {self.person.firstname} {self.person.lastname} {self.person.company_name} - {self.description}"
