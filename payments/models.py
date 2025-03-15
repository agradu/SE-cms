from django.db import models
from persons.models import Person
from invoices.models import Invoice
from services.models import DocumentBase, Currency
from django.conf import settings
from django.utils import timezone

# Create your models here.


class Payment(DocumentBase):
    type_choices = [("cash", "Cash"), ("bank", "Bank")]
    type = models.CharField(
        max_length=6,
        choices=type_choices,
        default="bank",
    )
    cancellation_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, default=None, related_name="cancellation_to_%(class)s")
    cancelled_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, default=None, related_name="cancelled_from_%(class)s")
    payment_date = models.DateField(default=timezone.now)
    is_recurrent = models.BooleanField(default=False)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"Paymant {self.serial}{self.number} ({self.type}) from {self.person} - {formatted_created_at} ({self.value}{self.currency.symbol})"
    
class PaymentElement(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)

    def __str__(self):
        return f"Inv. {self.invoice.serial}{self.invoice.number} from payment #{self.payment.id} ({self.payment.value}{self.payment.currency.symbol})"
