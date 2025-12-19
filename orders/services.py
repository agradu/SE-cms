from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.db.models import Sum, F, Value, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce

from orders.models import Order
from invoices.models import Invoice, InvoiceElement


class OrderService:
    @staticmethod
    def order_invoiced_total(order_id: int) -> Decimal:
        total_expr = ExpressionWrapper(
            F("element__quantity") * F("element__price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        return (
            InvoiceElement.objects
            .filter(
                element__order_id=order_id,
                invoice__cancellation_to__isnull=True,
                invoice__cancelled_from__isnull=True,
            )
            .aggregate(total=Coalesce(Sum(total_expr), Value(0, output_field=DecimalField())))
            .get("total")
            or Decimal("0")
        )

    @staticmethod
    def touch_linked_invoices(order: Order) -> None:
        invoice_ids = (
            InvoiceElement.objects
            .filter(element__order=order)
            .values_list("invoice_id", flat=True)
            .distinct()
        )
        for inv_id in invoice_ids:
            inv = Invoice.objects.filter(id=inv_id).first()
            if inv:
                inv.recalculate_from_elements(save=True)

    @staticmethod
    def sync_order_totals(order: Order, save: bool = True) -> None:
        order.recalculate_from_elements(save=True)
        order.invoiced = OrderService.order_invoiced_total(order.id)
        if save:
            order.save(update_fields=["invoiced"])
