# payments/views.py
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, F, Value, DecimalField, Prefetch
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
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

from payments.services import PaymentService


def _validation_error_to_text(e: ValidationError) -> str:
    if hasattr(e, "message_dict"):
        parts = []
        for field, msgs in e.message_dict.items():
            for m in msgs:
                parts.append(f"{field}: {m}")
        return " | ".join(parts) if parts else str(e)
    if hasattr(e, "messages"):
        return " | ".join(e.messages)
    return str(e)


@login_required(login_url="/login/")
def payments(request):
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)
    sort = request.GET.get("sort", "payment")

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
            "payed": p.value,
            "invoices": list(p.elements.all()),
        })

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

    serials = Serial.get_solo()
    is_recurrent = False

    new = (int(payment_id) == 0)
    payment_obj = None

    invoice = (
        Invoice.objects.select_related("currency").get(id=invoice_id)
        if invoice_id and int(invoice_id) > 0
        else None
    )
    is_client = invoice.is_client if invoice else True

    attached_invoice_ids = []
    payment_elements = []

    # ----------------------------
    # Load existing payment
    # ----------------------------
    if not new:
        payment_obj = get_object_or_404(
            Payment.objects.select_related("person", "currency"),
            id=payment_id
        )
        is_client = payment_obj.is_client

        payment_elements = list(
            PaymentElement.objects
            .filter(payment=payment_obj)
            .select_related("invoice", "invoice__currency")
            .order_by("invoice__created_at")
        )
        attached_invoice_ids = [pe.invoice_id for pe in payment_elements]

    # ----------------------------
    # Auto-create payment + attach invoice (GET flow)
    # ----------------------------
    if new and invoice:
        try:
            payment_obj = PaymentService.create_payment_with_invoice(
                person=person,
                invoice=invoice,
                serials=serials,
                user=request.user,
                payment_type="bank",
                payment_date=timezone.localdate(),
                description="",
                is_recurrent=is_recurrent,
                assign_serial_number=False,
                get_serial_and_number_func=get_serial_and_number,
            )
            # ✅ IMPORTANT: redirect so we reload in "existing payment" branch and show table reliably
            return redirect(
                "payment",
                payment_id=payment_obj.id,
                person_id=person.id,
                invoice_id=invoice.id,
            )
        except ValidationError as e:
            messages.warning(request, _validation_error_to_text(e))

    # ----------------------------
    # Unpaid invoices list (NET) for adding
    # IMPORTANT RULE:
    # - when adding invoices to an existing payment, show ONLY fully-unpaid invoices (total_paid == 0),
    #   because partially-paid invoices must be paid separately.
    # ----------------------------
    unpayed_qs = (
        Invoice.objects
        .filter(person=person, is_client=is_client)
        .exclude(id__in=attached_invoice_ids)
        .annotate(total_paid=Coalesce(Sum("payment_links__value"), Value(0, output_field=DecimalField())))
        .filter(total_paid__lt=F("value"))
        .order_by("deadline")
    )

    # If payment exists (we are in "add more invoices" mode), hide partially paid invoices
    if payment_obj and payment_obj.id:
        unpayed_qs = unpayed_qs.filter(total_paid=0)

    unpayed_elements = unpayed_qs

    # ----------------------------
    # POST actions
    # ----------------------------
    if request.method == "POST":
        form = request.POST

        payment_date = parse_payment_date(form.get("payment_date", ""), now)
        desc = form.get("payment_description", "")
        p_type = form.get("payment_type", payment_obj.type if payment_obj else "bank")

        try:
            with transaction.atomic():
                # ---- create if still new ----
                if new:
                    if not invoice:
                        return redirect("payment", payment_id=0, person_id=person.id, invoice_id=0)

                    payment_obj = PaymentService.create_payment_with_invoice(
                        person=person,
                        invoice=invoice,
                        serials=serials,
                        user=request.user,
                        payment_type=p_type,
                        payment_date=payment_date,
                        description=desc,
                        is_recurrent=is_recurrent,
                        assign_serial_number=True,
                        get_serial_and_number_func=get_serial_and_number,
                    )
                    new = False

                # ---- update header fields if existing ----
                else:
                    old_type = payment_obj.type
                    old_serial = payment_obj.serial
                    old_number = payment_obj.number

                    payment_obj.description = desc
                    payment_obj.type = p_type
                    payment_obj.payment_date = payment_date
                    payment_obj.modified_by = request.user
                    payment_obj.modified_at = now

                    # cash -> bank: drop receipt (only if it was last)
                    if old_type == "cash" and p_type == "bank" and old_serial and old_number:
                        last_payment = (
                            Payment.objects
                            .filter(type="cash", is_client=is_client)
                            .order_by("-id")
                            .first()
                        )
                        if last_payment and last_payment.id == payment_obj.id:
                            serials.receipt_number = max(1, serials.receipt_number - 1)
                            serials.save(update_fields=["receipt_number"])
                        payment_obj.serial = ""
                        payment_obj.number = ""

                    # bank -> cash: assign receipt if missing
                    elif old_type == "bank" and p_type == "cash" and not payment_obj.serial:
                        serial, number = get_serial_and_number(is_client, p_type, serials, assign=True)
                        payment_obj.serial = serial
                        payment_obj.number = number

                    payment_obj.save()

                # ---- element operations via service ----
                if "payment_element_id" in form and payment_obj:
                    PaymentService.remove_payment_element(payment_obj, int(form["payment_element_id"]))

                if "unpayed_element_id" in form and payment_obj:
                    inv = get_object_or_404(
                        Invoice,
                        id=int(form["unpayed_element_id"]),
                        person=person,
                        is_client=is_client,
                    )
                    PaymentService.add_invoice_to_payment(payment_obj, inv)

                if "payment_value" in form and payment_obj:
                    raw = form.get("payment_value")
                    try:
                        desired = Decimal(str(raw).strip().replace(",", "."))
                    except (InvalidOperation, TypeError, ValueError):
                        desired = None

                    if desired is not None:
                        PaymentService.set_single_invoice_amount(payment_obj, desired)

                # ---- FINAL: enforce + sync caches once ----
                PaymentService.enforce_no_partial_when_multiple(payment_obj)

                current_invoice_ids = list(
                    PaymentElement.objects
                    .filter(payment=payment_obj)
                    .values_list("invoice_id", flat=True)
                )
                PaymentService.sync_payment_and_invoices(payment_obj, current_invoice_ids)

                return redirect(
                    "payment",
                    payment_id=payment_obj.id if payment_obj else 0,
                    person_id=person.id,
                    invoice_id=invoice.id if invoice else 0
                )

        except ValidationError as e:
            messages.error(request, _validation_error_to_text(e))
        except Exception as e:
            messages.error(request, f"Eroare: {e}")

    # Reload elements for render
    if payment_obj and payment_obj.id:
        payment_elements = list(
            PaymentElement.objects
            .filter(payment=payment_obj)
            .select_related("invoice", "invoice__currency")
            .order_by("invoice__created_at")
        )

    return render(
        request,
        "payments/payment.html",
        {
            "person": person,
            "payment": payment_obj,
            "receipt_serial": payment_obj.serial if payment_obj else "",
            "receipt_number": payment_obj.number if payment_obj else "",
            "is_client": is_client,
            "payment_elements": payment_elements,
            "unpayed_elements": unpayed_elements,
            "new": new,
        },
    )


@login_required(login_url="/login/")
def print_receipt(request, payment_id):
    payment_obj = get_object_or_404(Payment.objects.select_related("person", "currency"), id=payment_id)
    payment_elements = (
        PaymentElement.objects
        .filter(payment=payment_obj)
        .select_related("invoice", "invoice__currency")
        .order_by("id")
    )
    leading_number = (payment_obj.number or "").rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        css_content = f.read()

    context = {
        "payment": payment_obj,
        "leading_number": leading_number,
        "payment_elements": payment_elements,
        "logo_base64": logo_base64,
        "value_in_words": num2words(payment_obj.value or 0, lang="de").capitalize(),
    }
    html_content = render_to_string("payments/print_receipt.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=css_content)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Beleg-{payment_obj.serial}-{payment_obj.number}.pdf'
    return response


@login_required(login_url="/login/")
def print_cancellation_receipt(request, payment_id):
    payment_obj = get_object_or_404(Payment.objects.select_related("person", "currency"), id=payment_id)
    payment_elements = (
        PaymentElement.objects
        .filter(payment=payment_obj)
        .select_related("invoice", "invoice__currency")
        .order_by("id")
    )
    leading_number = (payment_obj.number or "").rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        css_content = f.read()

    context = {
        "payment": payment_obj,
        "leading_number": leading_number,
        "payment_elements": payment_elements,
        "logo_base64": logo_base64,
        "value_in_words": num2words(payment_obj.value or 0, lang="de").capitalize(),
    }
    html_content = render_to_string("payments/print_cancellation_receipt.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=css_content)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Stornobeleg-{payment_obj.serial}-{payment_obj.number}.pdf'
    return response
