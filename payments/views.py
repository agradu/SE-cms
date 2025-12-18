from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils import timezone

from weasyprint import HTML, CSS
import base64
from num2words import num2words

from persons.models import Person
from invoices.models import Invoice
from payments.models import Payment, PaymentElement
from services.models import Serial

from common.helpers import get_date_range, get_search_params, paginate_objects
from .functions import get_serial_and_number, parse_payment_date


# ----------------------------
# Helpers (view-level)
# ----------------------------

def _invoice_remaining_net(invoice: Invoice) -> Decimal:
    """
    Remaining to pay NET, calculated from real allocations (PaymentElement),
    NOT from Payment.value.
    """
    paid = (
        PaymentElement.objects
        .filter(invoice_id=invoice.id)
        .aggregate(total=Coalesce(Sum("value"), Value(0, output_field=DecimalField())))
        .get("total")
        or Decimal("0")
    )
    return (invoice.value or Decimal("0")) - paid


def _sync_payment_and_invoices(payment: Payment, invoice_ids: list[int]) -> None:
    """
    Keep caches consistent after any operation.
    """
    payment.recalculate_from_elements(save=True)
    for inv_id in set(invoice_ids):
        try:
            inv = Invoice.objects.get(id=inv_id)
        except Invoice.DoesNotExist:
            continue
        inv.recalculate_payed_from_payments(save=True)


def _enforce_no_partial_when_multiple(payment: Payment) -> None:
    """
    If payment has more than one invoice element, each invoice must be paid in full (remaining).
    """
    elems = list(payment.elements.select_related("invoice"))
    if len(elems) <= 1:
        return

    for el in elems:
        inv = el.invoice
        remaining = _invoice_remaining_net(inv)
        # remaining computed includes THIS payment element too (if already saved),
        # so compute remaining excluding current element:
        paid_other = (
            PaymentElement.objects
            .filter(invoice_id=inv.id)
            .exclude(pk=el.pk)
            .aggregate(total=Coalesce(Sum("value"), Value(0, output_field=DecimalField())))
            .get("total")
            or Decimal("0")
        )
        remaining_excluding_this = (inv.value or Decimal("0")) - paid_other

        if el.value != remaining_excluding_this:
            raise ValueError(
                "Când un payment conține mai multe facturi, fiecare trebuie plătită integral (NET)."
            )


# ----------------------------
# Views
# ----------------------------

@login_required(login_url="/login/")
def payments(request):
    # filters
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)
    sort = request.GET.get("sort", "payment")

    # Base queryset
    qs = (
        Payment.objects
        .select_related("person", "currency", "modified_by", "created_by")
        .filter(
            Q(person__firstname__icontains=search_client) |
            Q(person__lastname__icontains=search_client) |
            Q(person__company_name__icontains=search_client),
            description__icontains=search_description,
            payment_date__range=(filter_start, filter_end)
        )
        .order_by("-id")
    )

    # Prefetch elements + invoices (avoid N+1 in template)
    from django.db.models import Prefetch
    elems_qs = (
        PaymentElement.objects
        .select_related("invoice", "payment", "invoice__currency", "invoice__person")
        .order_by("invoice__created_at")
    )
    qs = qs.prefetch_related(Prefetch("elements", queryset=elems_qs))

    person_payments = []
    for p in qs:
        person_payments.append({
            "payment": p,
            "payed": p.value,             # Payment.value = sum(elements.value) (NET)
            "invoices": list(p.elements.all()),
        })

    # Sorting (robust to nulls)
    def safe_str(x):
        return x or ""

    sort_keys = {
        "type": lambda x: safe_str(x["payment"].type),
        "payment": lambda x: x["payment"].id or 0,
        "person": lambda x: safe_str(getattr(x["payment"].person, "firstname", "")) + " " + safe_str(getattr(x["payment"].person, "lastname", "")),
        "receipt": lambda x: (safe_str(x["payment"].serial), safe_str(x["payment"].number)),
        "assignee": lambda x: safe_str(getattr(x["payment"].modified_by, "first_name", "")),
        "payed_at": lambda x: x["payment"].payment_date or timezone.localdate(),
        "value": lambda x: x["payment"].value or Decimal("0"),
        "update": lambda x: x["payment"].modified_at or timezone.now(),
    }

    sort_key = sort_keys.get(sort, lambda x: x["payment"].created_at or timezone.now())
    person_payments.sort(key=sort_key, reverse=(sort != "person"))

    payments_on_page = paginate_objects(request, person_payments)

    return render(
        request,
        "payments/payments.html",
        {
            "person_payments": payments_on_page,
            "sort": sort,
            "search_client": search_client,
            "search_description": search_description,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )


@login_required(login_url="/login/")
def payment(request, payment_id, person_id, invoice_id):
    now = timezone.now()
    person = get_object_or_404(Person, id=person_id)

    serials = Serial.get_solo()  # safer than id=1 hardcode
    is_recurrent = False

    new = (payment_id == 0)
    payment = None

    invoice = Invoice.objects.select_related("currency").get(id=invoice_id) if invoice_id and int(invoice_id) > 0 else None
    is_client = invoice.is_client if invoice else True

    attached_invoice_ids = []
    payment_elements = []

    # -----------------------------------
    # Load existing payment (edit mode)
    # -----------------------------------
    if not new:
        payment = get_object_or_404(
            Payment.objects.select_related("person", "currency"),
            id=payment_id
        )
        is_client = payment.is_client
        payment_elements = list(
            PaymentElement.objects
            .filter(payment=payment)
            .select_related("invoice", "invoice__currency")
            .order_by("invoice__created_at")
        )
        attached_invoice_ids = [pe.invoice_id for pe in payment_elements]

    # -----------------------------------
    # Create new payment (optional: auto attach invoice if provided)
    # -----------------------------------
    if new and invoice:
        with transaction.atomic():
            remaining = _invoice_remaining_net(invoice)
            if remaining > 0:
                default_type = "bank"
                serial, number = get_serial_and_number(is_client, default_type, serials, assign=False)

                payment = Payment.objects.create(
                    description="",
                    type=default_type,
                    serial=serial,
                    number=number,
                    person=person,
                    payment_date=timezone.localdate(),
                    is_client=is_client,
                    modified_by=request.user,
                    created_by=request.user,
                    currency=invoice.currency,
                    is_recurrent=is_recurrent,
                    value=Decimal("0"),  # se va recalcula din elements
                )
                PaymentElement.objects.create(payment=payment, invoice=invoice, value=remaining)

                _sync_payment_and_invoices(payment, [invoice.id])

                payment_elements = list(
                    PaymentElement.objects
                    .filter(payment=payment)
                    .select_related("invoice", "invoice__currency")
                    .order_by("invoice__created_at")
                )
                attached_invoice_ids = [invoice.id]
                new = False  # now it's a real payment

    # -----------------------------------
    # Unpaid invoices for this person (NET)
    # exclude invoices already attached to this payment
    # -----------------------------------
    unpayed_elements = (
        Invoice.objects
        .filter(person=person, is_client=is_client)
        .exclude(id__in=attached_invoice_ids)
        .annotate(total_paid=Coalesce(Sum("payment_links__value"), Value(0, output_field=DecimalField())))
        .filter(total_paid__lt=F("value"))
        .order_by("deadline")
    )

    # -----------------------------------
    # POST actions
    # -----------------------------------
    if request.method == "POST":
        form = request.POST

        payment_date = parse_payment_date(form.get("payment_date", ""), now)
        desc = form.get("payment_description", "")
        p_type = form.get("payment_type", payment.type if payment else "bank")

        with transaction.atomic():
            # If still new, require invoice and create payment first
            if new:
                if not invoice:
                    return redirect("payment", payment_id=0, person_id=person.id, invoice_id=0)

                remaining = _invoice_remaining_net(invoice)
                if remaining <= 0:
                    return redirect("payment", payment_id=0, person_id=person.id, invoice_id=invoice.id)

                serial, number = get_serial_and_number(is_client, p_type, serials, assign=True)

                payment = Payment.objects.create(
                    description=desc,
                    type=p_type,
                    serial=serial,
                    number=number,
                    person=person,
                    payment_date=payment_date,
                    is_client=is_client,
                    modified_by=request.user,
                    created_by=request.user,
                    currency=invoice.currency,
                    is_recurrent=is_recurrent,
                    value=Decimal("0"),
                )
                PaymentElement.objects.create(payment=payment, invoice=invoice, value=remaining)
                _sync_payment_and_invoices(payment, [invoice.id])
                new = False

            # Update existing payment fields
            else:
                old_type = payment.type
                old_serial = payment.serial
                old_number = payment.number

                payment.description = desc
                payment.type = p_type
                payment.payment_date = payment_date
                payment.modified_by = request.user
                payment.modified_at = now

                # switch cash -> bank: optionally drop receipt serial/number
                if old_type == "cash" and p_type == "bank" and old_serial and old_number:
                    last_payment = (
                        Payment.objects
                        .filter(type="cash", is_client=is_client)
                        .order_by("-id")
                        .first()
                    )
                    if last_payment and last_payment.id == payment.id:
                        serials.receipt_number = max(1, serials.receipt_number - 1)
                        serials.save(update_fields=["receipt_number"])
                    payment.serial = ""
                    payment.number = ""

                # switch bank -> cash: assign receipt if missing
                elif old_type == "bank" and p_type == "cash" and not payment.serial:
                    serial, number = get_serial_and_number(is_client, p_type, serials, assign=True)
                    payment.serial = serial
                    payment.number = number

                payment.save()

            touched_invoice_ids = []

            # Remove element (only if more than 1 element)
            if "payment_element_id" in form and payment:
                try:
                    elem_id = int(form["payment_element_id"])
                    if PaymentElement.objects.filter(payment=payment).count() > 1:
                        pe = PaymentElement.objects.filter(payment=payment, id=elem_id).first()
                        if pe:
                            touched_invoice_ids.append(pe.invoice_id)
                            pe.delete()
                except Exception:
                    pass

            # Add unpaid invoice to this payment
            if "unpayed_element_id" in form and payment:
                try:
                    inv = Invoice.objects.get(id=int(form["unpayed_element_id"]))
                    if inv.id not in attached_invoice_ids and not PaymentElement.objects.filter(payment=payment, invoice=inv).exists():
                        remaining = _invoice_remaining_net(inv)
                        if remaining > 0:
                            # By rule: if multiple invoices, must pay full remaining
                            PaymentElement.objects.create(payment=payment, invoice=inv, value=remaining)
                            touched_invoice_ids.append(inv.id)
                except (Invoice.DoesNotExist, ValueError):
                    pass

            # Set payment value (only allowed when payment has exactly 1 invoice)
            # This adjusts the single PaymentElement.value, then syncs caches.
            if "payment_value" in form and payment:
                try:
                    desired = Decimal(form.get("payment_value"))
                except (InvalidOperation, TypeError):
                    desired = None

                if desired is not None and desired > 0:
                    elems = list(PaymentElement.objects.filter(payment=payment).select_related("invoice"))
                    if len(elems) == 1:
                        pe = elems[0]
                        inv = pe.invoice

                        # max allowed = remaining excluding this element
                        paid_other = (
                            PaymentElement.objects
                            .filter(invoice_id=inv.id)
                            .exclude(pk=pe.pk)
                            .aggregate(total=Coalesce(Sum("value"), Value(0, output_field=DecimalField())))
                            .get("total")
                            or Decimal("0")
                        )
                        max_remaining = (inv.value or Decimal("0")) - paid_other
                        if desired <= max_remaining:
                            pe.value = desired
                            pe.full_clean()
                            pe.save(update_fields=["value"])
                            touched_invoice_ids.append(inv.id)

            # Enforce the rule: no partials when multiple invoices
            try:
                _enforce_no_partial_when_multiple(payment)
            except ValueError:
                # If violated, rollback the transaction
                raise

            # Sync caches
            if payment and payment.id:
                # also include any invoices currently attached
                current_invoice_ids = list(
                    PaymentElement.objects.filter(payment=payment).values_list("invoice_id", flat=True)
                )
                touched_invoice_ids.extend(current_invoice_ids)
                _sync_payment_and_invoices(payment, touched_invoice_ids)

            return redirect(
                "payment",
                payment_id=payment.id if payment else 0,
                person_id=person.id,
                invoice_id=invoice.id if invoice else 0
            )

    # Reload elements for GET render
    if payment and payment.id:
        payment_elements = list(
            PaymentElement.objects
            .filter(payment=payment)
            .select_related("invoice", "invoice__currency")
            .order_by("invoice__created_at")
        )

    return render(
        request,
        "payments/payment.html",
        {
            "person": person,
            "payment": payment,
            "receipt_serial": payment.serial if payment else "",
            "receipt_number": payment.number if payment else "",
            "is_client": is_client,
            "payment_elements": payment_elements,
            "unpayed_elements": unpayed_elements,
            "new": new,
        },
    )


@login_required(login_url="/login/")
def print_receipt(request, payment_id):
    payment = get_object_or_404(Payment.objects.select_related("person", "currency"), id=payment_id)
    payment_elements = (
        PaymentElement.objects
        .filter(payment=payment)
        .select_related("invoice", "invoice__currency")
        .order_by("id")
    )
    leading_number = (payment.number or "").rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        css_content = f.read()

    context = {
        "payment": payment,
        "leading_number": leading_number,
        "payment_elements": payment_elements,
        "logo_base64": logo_base64,
        "value_in_words": num2words(payment.value or 0, lang="de").capitalize(),
    }
    html_content = render_to_string("payments/print_receipt.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=css_content)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Beleg-{payment.serial}-{payment.number}.pdf'
    return response


@login_required(login_url="/login/")
def print_cancellation_receipt(request, payment_id):
    payment = get_object_or_404(Payment.objects.select_related("person", "currency"), id=payment_id)
    payment_elements = (
        PaymentElement.objects
        .filter(payment=payment)
        .select_related("invoice", "invoice__currency")
        .order_by("id")
    )
    leading_number = (payment.number or "").rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        css_content = f.read()

    context = {
        "payment": payment,
        "leading_number": leading_number,
        "payment_elements": payment_elements,
        "logo_base64": logo_base64,
        "value_in_words": num2words(payment.value or 0, lang="de").capitalize(),
    }
    html_content = render_to_string("payments/print_cancellation_receipt.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=css_content)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Stornobeleg-{payment.serial}-{payment.number}.pdf'
    return response
