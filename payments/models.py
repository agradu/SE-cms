from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum

from core.models import DocumentBase
from invoices.models import Invoice


class Payment(DocumentBase):
    class Type(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"

    type = models.CharField(
        max_length=6,
        choices=Type.choices,
        default=Type.BANK,
    )

    cancellation_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, default=None,
        related_name="cancellation_to_%(class)s"
    )
    cancelled_from = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, default=None,
        related_name="cancelled_from_%(class)s"
    )

    payment_date = models.DateField(default=timezone.localdate)
    is_recurrent = models.BooleanField(default=False)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        cur = self.currency.symbol if self.currency else ""
        return f"Payment {self.serial}{self.number} ({self.type}) from {self.person} - {formatted_created_at} ({self.value}{cur})"

    @property
    def is_cancelled(self) -> bool:
        return bool(self.cancellation_to_id or self.cancelled_from_id)

    def clean(self):
        super().clean()

        if self.value is not None and self.value < 0:
            raise ValidationError({"value": "value nu poate fi negativ."})

        if self.cancellation_to_id and self.cancellation_to_id == self.id:
            raise ValidationError({"cancellation_to": "Nu poți seta payment-ul ca anulare pentru el însuși."})

        if self.cancelled_from_id and self.cancelled_from_id == self.id:
            raise ValidationError({"cancelled_from": "Nu poți seta payment-ul ca anulat de el însuși."})

        if self.cancellation_to_id and self.cancelled_from_id:
            raise ValidationError("Payment-ul nu poate avea și cancellation_to și cancelled_from setate simultan.")

        # 🔒 REGULĂ BUSINESS
        elements = list(self.elements.select_related("invoice"))

        if len(elements) > 1:
            for el in elements:
                invoice = el.invoice
                remaining = (invoice.value or Decimal("0")) - (invoice.payed or Decimal("0"))
                if el.value != remaining:
                    raise ValidationError(
                        "Când un payment conține mai multe facturi, "
                        "fiecare trebuie plătită integral (NET)."
                    )

    def recalculate_from_elements(self, save: bool = True) -> Decimal:
        """
        Payment.value = suma PaymentElement.value (alocări pe facturi).
        """
        agg = self.elements.aggregate(total=Sum("value"))
        total = agg["total"] or Decimal("0")
        self.value = total
        if save:
            self.save(update_fields=["value"])
        return total

class PaymentElement(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="elements")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payment_links")
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        cur = self.payment.currency.symbol if self.payment and self.payment.currency else ""
        return (
            f"Inv. {self.invoice.serial}{self.invoice.number} "
            f"from payment #{self.payment_id} ({self.value}{cur})"
        )

    def clean(self):
        super().clean()

        if self.value is None or self.value <= 0:
            raise ValidationError({"value": "value trebuie să fie > 0."})

        if self.invoice.is_cancelled:
            raise ValidationError({"invoice": "Nu poți aloca plată pe o factură anulată."})

        # SUMĂ REALĂ plătită (fără cache)
        paid_so_far = (
            PaymentElement.objects
            .filter(invoice=self.invoice)
            .exclude(pk=self.pk)
            .aggregate(total=Sum("value"))["total"]
            or Decimal("0")
        )

        remaining = (self.invoice.value or Decimal("0")) - paid_so_far

        if self.value > remaining:
            raise ValidationError({
                "value": f"Suma depășește restul de plată NET ({remaining})."
            })
