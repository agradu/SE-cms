from __future__ import annotations

from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, DecimalField, ExpressionWrapper

from persons.models import Person  # păstrat pt. Proforma (redefinește person)
from orders.models import OrderElement
from services.models import DocumentBase


class Invoice(DocumentBase):
    # păstrăm același câmp (DateField) => fără schimbări de DB
    deadline = models.DateField(default=timezone.localdate)

    cancellation_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="cancellation_to_%(class)s",
    )
    cancelled_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="cancelled_from_%(class)s",
    )

    is_recurrent = models.BooleanField(default=False)

    # păstrăm câmpul existent (cache)
    payed = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M") if self.created_at else ""
        desc = self.description or ""
        return f"Invoice {self.serial}{self.number} from {formatted_created_at} - {self.person} - {desc}"

    # -----------------
    # Domain properties
    # -----------------
    @property
    def is_cancelled(self) -> bool:
        return bool(self.cancellation_to_id or self.cancelled_from_id)

    @property
    def remaining_to_pay(self) -> Decimal:
        # Atenție: aici presupunem că value = NET și payed = NET.
        # Dacă la tine plățile sunt GROSS, schimbăm la self.gross (din DocumentBase).
        val = self.value or Decimal("0")
        paid = self.payed or Decimal("0")
        return val - paid

    @property
    def is_paid(self) -> bool:
        return self.remaining_to_pay <= 0

    # -----------------
    # Domain actions
    # -----------------
    def register_payment(self, amount: Decimal, save: bool = True):
        """
        Folosește asta doar dacă TU vrei să împingi manual payed.
        Recomandarea OOP: payed să fie recalculat din PaymentElement (vezi recalculate_payed_from_payments).
        """
        if amount is None:
            return
        if amount < 0:
            raise ValueError("amount must be >= 0")
        self.payed = (self.payed or Decimal("0")) + amount
        if save:
            self.save(update_fields=["payed"])

    def recalculate_from_elements(self, save: bool = True) -> Decimal:
        """
        Recalculează value (NET) ca sumă a elementelor de comandă
        legate prin InvoiceElement: sum(element.quantity * element.price)
        """
        total_expr = ExpressionWrapper(
            F("element__quantity") * F("element__price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        agg = self.elements.aggregate(total=Sum(total_expr))
        total = agg["total"] or Decimal("0")
        self.value = total  # vat_value se poate recalcula în DocumentBase.save()
        if save:
            self.save()
        return total

    def recalculate_payed_from_payments(self, save: bool = True) -> Decimal:
        """
        Recalculează payed ca sumă a PaymentElement.value alocate pe această factură.
        Evită circular imports prin import local.
        """
        from payments.models import PaymentElement  # local import

        agg = PaymentElement.objects.filter(invoice_id=self.id).aggregate(total=Sum("value"))
        total = agg["total"] or Decimal("0")
        self.payed = total
        if save:
            self.save(update_fields=["payed"])
        return total

    # -----------------
    # Validation
    # -----------------
    def clean(self):
        super().clean()

        if self.payed is not None and self.payed < 0:
            raise ValidationError({"payed": "payed nu poate fi negativ."})

        # self-reference protection
        if self.id:
            if self.cancellation_to_id == self.id:
                raise ValidationError({"cancellation_to": "Nu poți seta invoice-ul ca anulare pentru el însuși."})
            if self.cancelled_from_id == self.id:
                raise ValidationError({"cancelled_from": "Nu poți seta invoice-ul ca anulat de el însuși."})

        # prevent contradictory links
        if self.cancellation_to_id and self.cancelled_from_id:
            raise ValidationError("Invoice-ul nu poate avea și cancellation_to și cancelled_from setate simultan.")

        # business rule: nu plătim peste value (NET)
        # (dacă la tine plățile sunt pe GROSS, schimbăm la self.gross)
        if self.value is not None and self.payed is not None and self.payed > self.value:
            raise ValidationError({"payed": "payed nu poate depăși value (net)."})

        # optional: nu factura pe un invoice anulat (în funcție de procesul tău)
        # if self.is_cancelled and self.value and self.value > 0:
        #     raise ValidationError("Nu poți avea valoare > 0 pe o factură anulată.")


class InvoiceElement(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="elements")
    element = models.ForeignKey(OrderElement, on_delete=models.CASCADE, related_name="invoice_links")

    def __str__(self):
        inv = f"{self.invoice.serial}{self.invoice.number}" if self.invoice_id else ""
        elm_ord = f"{self.element.order.serial}{self.element.order.number}"
        return f"Invoice element {self.element_id} from invoice {inv} / order {elm_ord}"

    def clean(self):
        super().clean()
        # optional: nu lega elemente de order diferit dacă ai o regulă de “o factură = un client”
        # if self.invoice and self.element and self.invoice.person_id != self.element.order.person_id:
        #     raise ValidationError("Elementul nu aparține aceluiași client ca factura.")


class Proforma(DocumentBase):
    # DocumentBase are deja person/is_client, dar în DB-ul tău sunt redefinite.
    # Păstrăm exact ca să evităm orice migrație/riscuri:
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    is_client = models.BooleanField(default=True)

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="proformas",
    )
    deadline = models.DateField(default=timezone.localdate)

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M") if self.created_at else ""
        desc = self.description or ""
        return f"Proforma {self.serial}{self.number} from {formatted_created_at} - {self.person} - {desc}"

    def recalculate_from_elements(self, save: bool = True) -> Decimal:
        """
        value (NET) = sum(element.quantity * element.price) prin ProformaElement.
        """
        total_expr = ExpressionWrapper(
            F("element__quantity") * F("element__price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        agg = self.elements.aggregate(total=Sum(total_expr))
        total = agg["total"] or Decimal("0")
        self.value = total
        if save:
            self.save()
        return total

    def clean(self):
        super().clean()
        # opțional: dacă proforma e legată de invoice, poate trebuie să fie același person
        # if self.invoice_id and self.person_id and self.invoice.person_id != self.person_id:
        #     raise ValidationError({"invoice": "Invoice-ul legat are alt person decât proforma."})


class ProformaElement(models.Model):
    proforma = models.ForeignKey(Proforma, on_delete=models.CASCADE, related_name="elements")
    element = models.ForeignKey(OrderElement, on_delete=models.CASCADE, related_name="proforma_links")

    def __str__(self):
        prof = f"{self.proforma.serial}{self.proforma.number}" if self.proforma_id else ""
        elm_ord = f"{self.element.order.serial}{self.element.order.number}"
        return f"Proforma element {self.element_id} from proforma {prof} / order {elm_ord}"

    def clean(self):
        super().clean()
        # opțional: aceeași regulă ca mai sus, dacă vrei consistență person/order
        # if self.proforma and self.element and self.proforma.person_id != self.element.order.person_id:
        #     raise ValidationError("Elementul nu aparține aceluiași client ca proforma.")
