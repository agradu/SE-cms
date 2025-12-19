from __future__ import annotations

from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce

from persons.models import Person  # păstrat pt. Proforma (redefinește person)
from orders.models import OrderElement
from core.models import DocumentBase


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

    # cache (NET) – plătit pe factură
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
        val = self.value or Decimal("0")
        paid = self.payed or Decimal("0")
        return val - paid

    @property
    def is_paid(self) -> bool:
        return self.remaining_to_pay <= 0

    # -----------------
    # Domain actions
    # -----------------
    def recalculate_from_elements(self, save: bool = True) -> Decimal:
        """
        Recalculează value (NET) ca sumă a elementelor de comandă
        legate prin InvoiceElement: sum(element.quantity * element.price)
        """
        total_expr = ExpressionWrapper(
            F("element__quantity") * F("element__price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        agg = self.elements.aggregate(total=Coalesce(Sum(total_expr), Decimal("0")))
        total = agg["total"] or Decimal("0")
        self.value = total
        if save:
            self.save()  # DocumentBase.save() îți poate recalcula vat_value
        return total

    def recalculate_payed_from_payments(self, save: bool = True) -> Decimal:
        """
        Recalculează payed ca sumă a PaymentElement.value (NET) alocate pe această factură.
        payment_links = related_name definit în PaymentElement.invoice
        """
        agg = self.payment_links.aggregate(total=Coalesce(Sum("value"), Decimal("0")))
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

        # self-reference protection
        if self.id:
            if self.cancellation_to_id == self.id:
                raise ValidationError({"cancellation_to": "Nu poți seta invoice-ul ca anulare pentru el însuși."})
            if self.cancelled_from_id == self.id:
                raise ValidationError({"cancelled_from": "Nu poți seta invoice-ul ca anulat de el însuși."})

        # prevent contradictory links
        if self.cancellation_to_id and self.cancelled_from_id:
            raise ValidationError("Invoice-ul nu poate avea și cancellation_to și cancelled_from setate simultan.")

        # allow negative payed ONLY for storno/cancellation invoices
        if self.payed is not None and self.payed < 0:
            if not (self.cancellation_to_id or (self.value is not None and self.value < 0)):
                raise ValidationError({"payed": "payed nu poate fi negativ."})

        # business rule: payed vs value (NET)
        if self.value is not None and self.payed is not None:
            if self.value >= 0:
                # normal invoice: cannot overpay
                if self.payed > self.value:
                    raise ValidationError({"payed": "payed nu poate depăși value (net)."})
            else:
                # storno invoice (value < 0): keep payed == value (negativ) by design
                if self.payed != self.value:
                    raise ValidationError({"payed": "La storno, payed trebuie să fie egal cu value (negativ)."})


class InvoiceElement(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="elements")
    element = models.ForeignKey(OrderElement, on_delete=models.CASCADE, related_name="invoice_links")

    def __str__(self):
        inv = f"{self.invoice.serial}{self.invoice.number}" if self.invoice_id else ""
        elm_ord = f"{self.element.order.serial}{self.element.order.number}"
        return f"Invoice element {self.element_id} from invoice {inv} / order {elm_ord}"

    def clean(self):
        super().clean()
        # opțional: reguli de consistență person/order
        # if self.invoice and self.element and self.invoice.person_id != self.element.order.person_id:
        #     raise ValidationError("Elementul nu aparține aceluiași client ca factura.")


class Proforma(DocumentBase):
    # păstrăm exact ca să evităm migrații
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
        total_expr = ExpressionWrapper(
            F("element__quantity") * F("element__price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        agg = self.elements.aggregate(total=Coalesce(Sum(total_expr), Decimal("0")))
        total = agg["total"] or Decimal("0")
        self.value = total
        if save:
            self.save()
        return total

    def clean(self):
        super().clean()
        # opțional: dacă proforma e legată de invoice, poate trebuie același person
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
