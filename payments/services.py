# payments/services.py
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Callable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from invoices.models import Invoice
from payments.models import Payment, PaymentElement


GetSerialAndNumberFn = Callable[[bool, str, object, bool], tuple[str, str]]
# signature: (is_client, payment_type, serials, assign) -> (serial, number)


class PaymentService:
    """
    Domain/service layer for Payment orchestration:
    - calculates remaining amounts using real allocations (PaymentElement)
    - enforces business rules:
        (1) no partial payments when a payment covers multiple invoices
        (2) invoices already partially paid must be paid separately (cannot be added to a multi-invoice payment)
    - keeps caches consistent (Payment.value and Invoice.payed)
    """

    # ----------------------------
    # Core calculations
    # ----------------------------

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
        return total

    @staticmethod
    def invoice_remaining_net(invoice: Invoice, exclude_element_id: int | None = None) -> Decimal:
        paid = PaymentService.invoice_paid_net(invoice, exclude_element_id=exclude_element_id)
        return (invoice.value or Decimal("0")) - paid

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
        If payment has > 1 invoice element, each element must equal the invoice remaining
        (excluding this element), i.e. pay full NET remaining for each invoice.
        """
        elems = list(payment.elements.select_related("invoice"))
        if len(elems) <= 1:
            return

        for el in elems:
            inv = el.invoice
            remaining_excluding_this = PaymentService.invoice_remaining_net(inv, exclude_element_id=el.pk)
            if el.value != remaining_excluding_this:
                raise ValidationError(
                    "Când un payment conține mai multe facturi, fiecare trebuie plătită integral (NET)."
                )

    @staticmethod
    def enforce_partially_paid_invoice_must_be_separate(payment: Payment, invoice: Invoice) -> None:
        """
        Rule: if an invoice is already partially paid (paid_net > 0),
        it must NOT be added to a payment that already has at least one other invoice.
        (i.e. partially paid invoices must be paid in a separate payment)
        """
        paid_net = PaymentService.invoice_paid_net(invoice)
        if paid_net > 0:
            # if we are about to have multiple invoices in this payment, forbid
            has_other = payment.elements.exclude(invoice_id=invoice.id).exists()
            if has_other:
                raise ValidationError(
                    {"invoice": "Factura este plătită parțial și trebuie achitată separat (nu la grămadă cu altele)."}
                )

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
        """
        Creates a Payment and attaches exactly one invoice with full remaining NET.
        Serial/number generation is injected via get_serial_and_number_func.
        """
        if invoice.is_cancelled:
            raise ValidationError({"invoice": "Nu poți aloca plată pe o factură anulată."})

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

            # For a single-invoice payment, partially paid invoices are allowed (this is the "separately" case).
            PaymentService.enforce_no_partial_when_multiple(payment)
            PaymentService.sync_payment_and_invoices(payment, [invoice.id])

            return payment

    @staticmethod
    def add_invoice_to_payment(payment: Payment, invoice: Invoice) -> PaymentElement:
        """
        Adds an invoice to a payment by creating a PaymentElement with full remaining NET.
        Enforces:
          - no partials when multiple invoices
          - partially paid invoices must be paid separately (cannot be added when payment already contains another invoice)
        """
        if invoice.is_cancelled:
            raise ValidationError({"invoice": "Nu poți aloca plată pe o factură anulată."})

        if PaymentElement.objects.filter(payment=payment, invoice=invoice).exists():
            raise ValidationError({"invoice": "Factura este deja atașată acestui payment."})

        remaining = PaymentService.invoice_remaining_net(invoice)
        if remaining <= 0:
            raise ValidationError({"invoice": "Factura este deja plătită (NET)."})

        with transaction.atomic():
            # Create element first
            pe = PaymentElement(payment=payment, invoice=invoice, value=remaining)
            pe.full_clean()
            pe.save()

            # Enforce new business rule AFTER creation (payment now includes it)
            PaymentService.enforce_partially_paid_invoice_must_be_separate(payment, invoice)

            PaymentService.enforce_no_partial_when_multiple(payment)
            PaymentService.sync_payment_and_invoices(payment, [invoice.id])

            return pe

    @staticmethod
    def remove_payment_element(payment: Payment, element_id: int) -> None:
        """
        Removes a PaymentElement from the payment, but only if payment has >1 elements.
        Enforces rule and syncs caches.
        """
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
    def set_single_invoice_amount(payment: Payment, desired: Decimal) -> None:
        """
        Allowed only when payment has exactly 1 invoice element.
        Sets PaymentElement.value to desired (NET), respecting remaining NET for that invoice.
        """
        if desired is None or desired <= 0:
            raise ValidationError({"payment_value": "Suma trebuie să fie > 0."})

        elems = list(payment.elements.select_related("invoice"))
        if len(elems) != 1:
            raise ValidationError("Poți seta suma manual doar când payment-ul are exact 1 factură.")

        pe = elems[0]
        inv = pe.invoice

        max_remaining = PaymentService.invoice_remaining_net(inv, exclude_element_id=pe.pk)
        if desired > max_remaining:
            raise ValidationError({"payment_value": f"Suma depășește restul de plată NET ({max_remaining})."})

        with transaction.atomic():
            pe.value = desired
            pe.full_clean()
            pe.save(update_fields=["value"])

            PaymentService.enforce_no_partial_when_multiple(payment)
            PaymentService.sync_payment_and_invoices(payment, [inv.id])
