from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.apps import apps
from django.db import transaction

from core.models import DocumentBase, DocumentElement, Status


class Order(DocumentBase):
    deadline = models.DateTimeField(default=timezone.now)
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)
    invoiced = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        formatted_deadline = self.deadline.strftime("%d.%m.%Y %H:%M")
        cur = self.currency.symbol if self.currency else ""
        desc = self.description or ""
        return f"Order {self.serial}{self.number} - {self.person} - {formatted_deadline} - {desc} ({self.value}{cur})"

    # ------- OOP: totals / invoicing -------

    @property
    def remaining_to_invoice(self) -> Decimal:
        val = self.value or Decimal("0")
        inv = self.invoiced or Decimal("0")
        return val - inv

    @property
    def is_fully_invoiced(self) -> bool:
        return self.remaining_to_invoice <= 0

    def register_invoiced(self, amount: Decimal, save: bool = True):
        if amount is None:
            return
        if amount < 0:
            raise ValueError("amount must be >= 0")
        self.invoiced = (self.invoiced or Decimal("0")) + amount
        if save:
            self.save(update_fields=["invoiced"])

    def recalculate_from_elements(self, save: bool = True) -> Decimal:
        """
        Recalculează value (NET) ca sumă a elementelor.
        Nu schimbă DB schema; doar menține consistența.
        """
        total_expr = ExpressionWrapper(
            F("quantity") * F("price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        agg = self.elements.aggregate(total=Sum(total_expr))
        total = agg["total"] or Decimal("0")
        self.value = total
        # vat_value se va recalcula în DocumentBase.save() (dacă păstrăm acel comportament)
        if save:
            self.save()
        return total

    def clean(self):
        super().clean()
        if self.invoiced is not None and self.invoiced < 0:
            raise ValidationError({"invoiced": "invoiced nu poate fi negativ."})
        # opțional: nu poți factura mai mult decât valoarea comenzii
        if self.value is not None and self.invoiced is not None and self.invoiced > self.value:
            raise ValidationError({"invoiced": "invoiced nu poate depăși value (net)."})
        
    def _related_invoices_queryset(self):
        Invoice = apps.get_model("invoices", "Invoice")
        # Invoice -> InvoiceElement (related_name="elements") -> OrderElement (field "element") -> order
        return Invoice.objects.filter(elements__element__order_id=self.id).distinct()

    def _related_proformas_queryset(self):
        Proforma = apps.get_model("invoices", "Proforma")
        return Proforma.objects.filter(elements__element__order_id=self.id).distinct()

    def propagate_vat_rate_to_related_docs(self):
        """
        Propagă vat_rate către toate Invoice/Proforma legate de acest Order prin OrderElement.
        Recalculează vat_value prin save() (DocumentBase.save()).
        """
        new_rate = self.vat_rate or Decimal("0")

        invoices = list(self._related_invoices_queryset())
        for inv in invoices:
            if inv.vat_rate != new_rate:
                inv.vat_rate = new_rate
                inv.save(update_fields=["vat_rate"])  # vat_value se recalculează în DocumentBase.save()

        proformas = list(self._related_proformas_queryset())
        for prof in proformas:
            if prof.vat_rate != new_rate:
                prof.vat_rate = new_rate
                prof.save(update_fields=["vat_rate"])

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        # dacă update_fields e set și nu conține vat_rate, nu are sens să verifici/propagezi
        if update_fields is not None and "vat_rate" not in set(update_fields):
            return super().save(*args, **kwargs)

        vat_changed = False
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values_list("vat_rate", flat=True).first()
            vat_changed = (old != self.vat_rate)

        with transaction.atomic():
            super().save(*args, **kwargs)
            if vat_changed:
                self.propagate_vat_rate_to_related_docs()

class OrderElement(DocumentElement):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="elements")
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)

    def __str__(self):
        cur = self.order.currency.symbol if self.order and self.order.currency else ""
        um = self.um.name if self.order and self.um else ""
        svc = self.service.name if self.service else (self.description or "—")
        elm_ord = f"{self.order.serial}{self.order.number}"
        return f"Elm. #{self.id} from order {elm_ord} - {svc} ({self.price} {cur} * {self.quantity} {um})"


    def clean(self):
        super().clean()
        # exemplu: dacă order are currency, elementul ar trebui să fie implicit în aceeași logică (nu ai currency pe element)
        # aici poți impune reguli de status vs order.status, dacă e cazul

class Offer(DocumentBase):
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, default=None, related_name="offers")
    deadline = models.DateTimeField(default=timezone.now)
    status = models.ForeignKey(Status, on_delete=models.SET_DEFAULT, default=1)

    def __str__(self):
        formatted_deadline = self.deadline.strftime("%d.%m.%Y %H:%M")
        cur = self.currency.symbol if self.currency else ""
        desc = self.description or ""
        return f"Offer {self.serial}{self.number} - {self.person} - {formatted_deadline} - {desc} ({self.value}{cur})"

    def recalculate_from_elements(self, save: bool = True):
        total_expr = ExpressionWrapper(
            F("quantity") * F("price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        agg = self.elements.aggregate(total=Sum(total_expr))
        total = agg["total"] or Decimal("0")
        self.value = total
        if save:
            self.save()
        return total
        

class OfferElement(DocumentElement):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="elements")

    def __str__(self):
        cur = self.offer.currency.symbol if self.offer and self.offer.currency else ""
        um = self.um.name if self.offer and self.um else ""
        svc = self.service.name if self.service else (self.description or "—")
        elm_off = f"{self.offer.serial}{self.offer.number}"
        return f"Elm. #{self.id} from offer {elm_off} - {svc} ({self.price} {cur} * {self.quantity} {um})"
