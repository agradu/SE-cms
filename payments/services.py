# payments/services.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Callable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from invoices.models import Invoice
from payments.models import Payment, PaymentElement


TWOPLACES = Decimal("0.01")

GetSerialAndNumberFn = Callable[[bool, str, object, bool], tuple[str, str]]
# signature: (is_client, payment_type, serials, assign) -> (serial, number)


class PaymentService:
    """
    Domain/service layer for Payment orchestration:
    - calculates remaining amounts using real allocations (PaymentElement)
    - enforces business rule: no partial payments when a payment covers multiple invoices
    - keeps caches consistent (Payment.value and Invoice.payed)
    - UX improvements:
        * when setting a value too high -> clamp to max
        * when adding a 2nd invoice -> auto-fill first invoice to full remaining
    """

    # ----------------------------
    # Core calculations (NET)
    # ----------------------------

    @staticmethod
    def _q2(x: Decimal) -> Decimal:
        return (x or Decimal("0")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    @staticmethod
    def invoice_paid_net(invoice: Invoice, exclude_element_id: int | None = None) -> Decimal:
        qs = PaymentElement.objects.filter(invoice_id=invoice.id)
        if exclude_element_id:
            qs = qs.exclude(pk=exclude_element_id)

        total = (
            qs.aggregate(total=Coalesce(Sum("value"), Value(0, output_field=DecimalField())))
            .get("total")
            or Decimal("0")
        )
        return PaymentService._q2(total)

    @staticmethod
    def invoice_remaining_net(invoice: Invoice, exclude_element_id: int | None = None) -> Decimal:
        paid = PaymentService.invoice_paid_net(invoice, exclude_element_id=exclude_element_id)
        remaining = (invoice.value or Decimal("0")) - paid
        return PaymentService._q2(remaining)

    # ----------------------------
    # Consistency / caches
    # ----------------------------

    @staticmethod
    def sync_payment_and_invoices(payment: Payment, invoice_ids: Iterable[int]) -> None:
        """
        Recompute:
          - Payment.value from its elements
          - Invoice.payed from PaymentElement allocations
        """
        payment.recalculate_from_elements(save=True)

        for inv_id in set(int(x) for x in invoice_ids if x):
            try:
                inv = Invoice.objects.get(id=inv_id)
            except Invoice.DoesNotExist:
                continue
            inv.recalculate_payed_from_payments(save=True)

    # ----------------------------
    # Business rules
    # ----------------------------

    @staticmethod
    def enforce_no_partial_when_multiple(payment: Payment) -> None:
        """
        If payment has > 1 invoice element, each element must equal invoice remaining
        (excluding this element), i.e. pay full NET remaining for each invoice.
        """
        elems = list(payment.elements.select_related("invoice"))
        if len(elems) <= 1:
            return

        for el in elems:
            inv = el.invoice
            required = PaymentService.invoice_remaining_net(inv, exclude_element_id=el.pk)
            required = PaymentService._q2(required)
            current = PaymentService._q2(el.value or Decimal("0"))

            if current != required:
                raise ValidationError(
                    "Când un payment conține mai multe facturi, fiecare trebuie plătită integral (NET)."
                )

    # ----------------------------
    # Internal helpers
    # ----------------------------

    @staticmethod
    def _ensure_invoice_not_cancelled(invoice: Invoice) -> None:
        if invoice.is_cancelled:
            raise ValidationError({"invoice": "Nu poți aloca plată pe o factură anulată."})

    @staticmethod
    def _ensure_payment_single_element_is_full_remaining_if_needed(payment: Payment) -> None:
        """
        UX fix:
        If user is about to make payment cover multiple invoices,
        then the existing single element must be full remaining.
        We'll auto-adjust it to remaining (excluding itself).
        """
        elems = list(payment.elements.select_related("invoice"))
        if len(elems) != 1:
            return

        pe = elems[0]
        inv = pe.invoice

        required = PaymentService.invoice_remaining_net(inv, exclude_element_id=pe.pk)
        required = PaymentService._q2(required)

        current = PaymentService._q2(pe.value or Decimal("0"))

        # Only adjust if required is positive; if required <= 0, invoice is already fully covered elsewhere
        if required <= 0:
            return

        if current != required:
            pe.value = required
            pe.full_clean()
            pe.save(update_fields=["value"])

    # ----------------------------
    # High-level operations
    # ----------------------------

    @staticmethod
    def create_payment_with_invoice(
        *,
        person,
        invoice: Invoice,
        serials,
        user,
        payment_type: str,
        payment_date,
        description: str,
        is_recurrent: bool,
        assign_serial_number: bool,
        get_serial_and_number_func: GetSerialAndNumberFn,
    ) -> Payment:
        PaymentService._ensure_invoice_not_cancelled(invoice)

        if invoice.person_id and person and invoice.person_id != person.id:
            raise ValidationError({"invoice": "Factura nu aparține acestui client/provider."})

        remaining = PaymentService.invoice_remaining_net(invoice)
        if remaining <= 0:
            raise ValidationError({"invoice": "Factura este deja plătită (NET)."})

        if payment_date is None:
            payment_date = timezone.localdate()

        serial, number = get_serial_and_number_func(
            invoice.is_client, payment_type, serials, assign=assign_serial_number
        )

        with transaction.atomic():
            payment = Payment.objects.create(
                description=description or "",
                type=payment_type,
                serial=serial,
                number=number,
                person=person,
                payment_date=payment_date,
                is_client=invoice.is_client,
                modified_by=user,
                created_by=user,
                currency=invoice.currency,
                is_recurrent=is_recurrent,
                value=Decimal("0"),
            )

            pe = PaymentElement(payment=payment, invoice=invoice, value=remaining)
            pe.full_clean()
            pe.save()

            PaymentService.sync_payment_and_invoices(payment, [invoice.id])
            return payment

    @staticmethod
    def add_invoice_to_payment(payment: Payment, invoice: Invoice) -> PaymentElement:
        """
        Adds an invoice to a payment by creating a PaymentElement with full remaining NET.

        IMPORTANT UX fix:
        - If payment currently has exactly 1 invoice, we auto-adjust that existing element
          to full remaining BEFORE adding the new invoice, so user doesn't get blocked.
        """
        PaymentService._ensure_invoice_not_cancelled(invoice)

        if PaymentElement.objects.filter(payment=payment, invoice=invoice).exists():
            raise ValidationError({"invoice": "Factura este deja atașată acestui payment."})

        remaining = PaymentService.invoice_remaining_net(invoice)
        if remaining <= 0:
            raise ValidationError({"invoice": "Factura este deja plătită (NET)."})

        with transaction.atomic():
            # ✅ auto-fill existing single element to full remaining if we are going multi-invoice
            PaymentService._ensure_payment_single_element_is_full_remaining_if_needed(payment)

            pe = PaymentElement(payment=payment, invoice=invoice, value=remaining)
            pe.full_clean()
            pe.save()

            # rule check + cache sync
            PaymentService.enforce_no_partial_when_multiple(payment)
            current_invoice_ids = list(payment.elements.values_list("invoice_id", flat=True))
            PaymentService.sync_payment_and_invoices(payment, current_invoice_ids)

            return pe

    @staticmethod
    def remove_payment_element(payment: Payment, element_id: int) -> None:
        try:
            pe = PaymentElement.objects.select_related("invoice").get(id=element_id, payment=payment)
        except PaymentElement.DoesNotExist:
            return

        if payment.elements.count() <= 1:
            raise ValidationError("Nu poți șterge singurul element dintr-un payment.")

        invoice_id = pe.invoice_id

        with transaction.atomic():
            pe.delete()

            PaymentService.enforce_no_partial_when_multiple(payment)
            current_invoice_ids = list(payment.elements.values_list("invoice_id", flat=True))
            PaymentService.sync_payment_and_invoices(payment, [invoice_id, *current_invoice_ids])

    @staticmethod
    def set_single_invoice_amount(payment: Payment, desired: Decimal) -> Decimal:
        """
        Allowed only when payment has exactly 1 invoice element.
        If desired > max allowable -> clamp to max (as user requested).
        Returns the final applied value.
        """
        if desired is None:
            raise ValidationError({"payment_value": "Suma lipsește."})

        try:
            desired = PaymentService._q2(Decimal(desired))
        except Exception:
            raise ValidationError({"payment_value": "Suma nu este validă."})

        if desired <= 0:
            raise ValidationError({"payment_value": "Suma trebuie să fie > 0."})

        elems = list(payment.elements.select_related("invoice"))
        if len(elems) != 1:
            raise ValidationError("Poți seta suma manual doar când payment-ul are exact 1 factură.")

        pe = elems[0]
        inv = pe.invoice

        max_remaining = PaymentService.invoice_remaining_net(inv, exclude_element_id=pe.pk)

        if max_remaining <= 0:
            raise ValidationError({"payment_value": "Factura este deja acoperită (NET)."})

        # ✅ clamp
        applied = desired if desired <= max_remaining else max_remaining
        applied = PaymentService._q2(applied)

        with transaction.atomic():
            pe.value = applied
            pe.full_clean()
            pe.save(update_fields=["value"])

            PaymentService.sync_payment_and_invoices(payment, [inv.id])

        return applied
