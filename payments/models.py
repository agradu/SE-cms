from django.db import models
from persons.models import Person
from invoices.models import Invoice
from services.models import Currency
from django.conf import settings
from django.utils import timezone

# Create your models here.


class Payment(models.Model):
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
    type_choices = [("cash", "Cash"), ("bank", "Bank")]
    type = models.CharField(
        max_length=6,
        choices=type_choices,
        default="bank",
    )
    is_client = models.BooleanField(default=True)
    serial = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=20, blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.ForeignKey(
        Currency, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    description = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"Paymant ({self.type}) from {self.person} - {formatted_created_at} ({self.value}{self.currency.symbol})"
    
class PaymentElement(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)

    def __str__(self):
        return f"Invoice #{self.invoice.id} from payment #{self.payment.id} ({self.payment.value}{self.payment.value})"
