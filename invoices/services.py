from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, F, Value, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce

from invoices.models import Invoice, InvoiceElement, Proforma
from orders.models import Order, OrderElement


class InvoiceService:
    # ----------------------------
    # Low-level expressions
    # ----------------------------
    @staticmethod
    def _invoice_elements_total_expr(prefix: str = "element__") -> ExpressionWrapper:
        return ExpressionWrapper(
            F(f"{prefix}quantity") * F(f"{prefix}price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )

    # ----------------------------
    # Sync / caches
    # ----------------------------
    @staticmethod
    def sync_invoice_after_elements(invoice: Invoice) -> None:
        """
        Recalc invoice.value from links; for storno keep negative + payed=value (negative),
        else recalc vat + recalc payed from payments.
        """
        invoice.recalculate_from_elements(save=False)

        if invoice.cancellation_to_id:
            invoice.value = -abs(invoice.value or Decimal("0"))
            invoice.payed = invoice.value  # negativ
            invoice.save()  # DocumentBase.save() poate recalcula TVA
        else:
            invoice.save()
            invoice.recalculate_payed_from_payments(save=True)

    @staticmethod
    def sync_proforma_after_elements(proforma: Proforma) -> None:
        proforma.recalculate_from_elements(save=True)

    # ----------------------------
    # Order.invoiced cache
    # ----------------------------
    @staticmethod
    def recalculate_order_invoiced_for_orders(order_ids: Iterable[int]) -> None:
        order_ids = set(int(x) for x in order_ids if x)
        if not order_ids:
            return

        total_expr = InvoiceService._invoice_elements_total_expr(prefix="element__")

        for oid in order_ids:
            total = (
                InvoiceElement.objects
                .filter(
                    element__order_id=oid,
                    invoice__cancellation_to__isnull=True,
                    invoice__cancelled_from__isnull=True,
                )
                .aggregate(total=Coalesce(Sum(total_expr), Value(0, output_field=DecimalField())))
                .get("total")
                or Decimal("0")
            )
            Order.objects.filter(id=oid).update(invoiced=total)

    # ----------------------------
    # High-level operations
    # ----------------------------
    @staticmethod
    @transaction.atomic
    def create_cancellation_invoice(*, cancelled_invoice: Invoice, user, serials) -> Invoice:
        """
        Create storno invoice:
        - create new invoice with cancellation_to
        - set cancelled_invoice.cancelled_from
        - copy InvoiceElements
        - sync totals and Order.invoiced
        - increment serials.invoice_number
        """
        if cancelled_invoice.is_cancelled:
            raise ValidationError({"invoice": "Factura este deja anulată / are legătură de storno."})

        cancellation = Invoice.objects.create(
            serial=serials.invoice_serial,
            number=str(serials.invoice_number),
            person=cancelled_invoice.person,
            is_client=cancelled_invoice.is_client,
            modified_by=user,
            created_by=user,
            currency=cancelled_invoice.currency,
            cancellation_to=cancelled_invoice,
            description="Stornorechnung",
            value=Decimal("0"),
            payed=Decimal("0"),
            vat_rate=cancelled_invoice.vat_rate,
        )

        cancelled_invoice.cancelled_from = cancellation
        cancelled_invoice.save(update_fields=["cancelled_from"])

        src_element_ids = list(
            InvoiceElement.objects.filter(invoice=cancelled_invoice).values_list("element_id", flat=True)
        )
        for eid in src_element_ids:
            InvoiceElement.objects.create(invoice=cancellation, element_id=eid)

        InvoiceService.sync_invoice_after_elements(cancellation)

        order_ids = set(
            OrderElement.objects.filter(id__in=src_element_ids).values_list("order_id", flat=True)
        )
        InvoiceService.recalculate_order_invoiced_for_orders(order_ids)

        serials.invoice_number += 1
        serials.save(update_fields=["invoice_number"])

        return cancellation
