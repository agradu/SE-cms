from django.db import models
from persons.models import Person
from invoices.models import Invoice
from receipts.models import Receipt
from services.models import Currency
from django.conf import settings
from django.utils import timezone

# Create your models here.


class Payment(models.Model):
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='created_by_%(class)s', on_delete=models.SET_NULL, null=True, blank=True
    )
    modified_at = models.DateTimeField(default=timezone.now)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='modified_by_%(class)s', on_delete=models.SET_NULL, null=True, blank=True
    )
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    type_choices = [
        ("cash", "Cash"),
        ("bank", "Bank")
    ]
    type = models.CharField(
        max_length=6,
        choices=type_choices,
        default="bank",
    )
    receipt = models.ForeignKey(
        Receipt, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    description = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"Paymant ({self.type}) {self.receipt} from {self.person} - {formatted_created_at} ({self.value}{self.currency.symbol})"

class PaymentInvoice(models.Model):
    payment = models.ForeignKey(Receipt, on_delete=models.CASCADE)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    
    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"Pay.{self.payment.serial}{self.payment.number} inv.{self.invoice.serial}{self.invoice.number}"
