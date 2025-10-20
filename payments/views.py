from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, F
from persons.models import Person
from orders.models import Order, OrderElement
from invoices.models import Invoice, InvoiceElement
from payments.models import Payment, PaymentElement
from services.models import Currency, Status, Service, UM, Serial
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils.dateparse import parse_date
from django.utils import timezone
from weasyprint import HTML, CSS
import base64
from decimal import Decimal
from num2words import num2words
from common.helpers import get_date_range, get_search_params, paginate_objects
from .functions import update_invoice_payed, get_serial_and_number, parse_payment_date, set_payment_value

# Create your views here.

@login_required(login_url="/login/")
def payments(request):
    # Get data and filters
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)

    sort = request.GET.get("sort", "payment")
    
    # Query payments in a single filter operation
    selected_payments = Payment.objects.filter(
        Q(person__firstname__icontains=search_client) |
        Q(person__lastname__icontains=search_client) |
        Q(person__company_name__icontains=search_client),
        description__icontains=search_description,
        payment_date__range=(filter_start, filter_end)
    )
    
    # Fetch payment elements efficiently
    person_payments = [
        {"payment": p, "payed": p.value, "invoices": PaymentElement.objects.filter(payment=p)}
        for p in selected_payments
    ]

    # Sorting logic
    sort_keys = {
        "type": lambda x: x["payment"].type,
        "payment": lambda x: x["payment"].id,
        "person": lambda x: x["payment"].person.firstname,
        "receipt": lambda x: (x["payment"].serial, x["payment"].number),
        "assignee": lambda x: x["payment"].modified_by.first_name,
        "payed_at": lambda x: x["payment"].payment_date,
        "value": lambda x: x["payment"].value,
        "update": lambda x: x["payment"].modified_at,
    }

    sort_key = sort_keys.get(sort, lambda x: x["payment"].created_at)
    person_payments.sort(key=sort_key, reverse=(sort != "person"))

    # Pagination
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
    date_now = timezone.now()
    person = get_object_or_404(Person, id=person_id)
    serials = Serial.objects.get(id=1)
    is_recurrent = False
    new = payment_id == 0
    payment = None
    invoice = Invoice.objects.get(id=invoice_id) if invoice_id > 0 else None
    is_client = invoice.is_client if invoice else True

    if not new:
        payment = get_object_or_404(Payment, id=payment_id)
        is_client = payment.is_client
        payment_elements = PaymentElement.objects.filter(payment=payment).order_by("invoice__created_at")
        attached_invoice_ids = list(payment_elements.values_list("invoice_id", flat=True))
    else:
        payment_elements = []
        attached_invoice_ids = []
        if invoice:
            total_payed = PaymentElement.objects.filter(invoice=invoice).aggregate(total=Sum("value"))["total"] or 0
            if total_payed < invoice.value:
                remaining = invoice.value - total_payed
                default_type = "bank"
                serial, number = get_serial_and_number(is_client, default_type, serials, assign=False)
                payment = Payment.objects.create(
                    description="",
                    type=default_type,
                    serial=serial,
                    number=number,
                    person=person,
                    payment_date=date_now,
                    is_client=is_client,
                    modified_by=request.user,
                    created_by=request.user,
                    currency=invoice.currency,
                    is_recurrent=is_recurrent,
                    value=remaining
                )
                PaymentElement.objects.create(payment=payment, invoice=invoice, value=remaining)
                update_invoice_payed(invoice)
                payment_elements = PaymentElement.objects.filter(payment=payment).order_by("invoice__created_at")
                attached_invoice_ids = [invoice.id]
                new = False  # IMPORTANT!

    unpayed_elements = Invoice.objects.filter(
        person=person,
        is_client=is_client
    ).exclude(
        id__in=attached_invoice_ids
    ).annotate(
        total_payed=Sum("paymentelement__value")
    ).filter(
        Q(total_payed__lt=F("value")) | Q(total_payed__isnull=True)
    )

    if request.method == "POST":
        form = request.POST
        payment_date = parse_payment_date(form.get("payment_date", ""), date_now)
        desc = form.get("payment_description", "")
        p_type = form.get("payment_type", payment.type if payment else "bank")

        # Setare serial & număr dacă este cash
        if new:
            if not invoice or invoice.id in attached_invoice_ids:
                return redirect("payment", payment_id=0, person_id=person.id, invoice_id=invoice.id if invoice else 0)

            total_payed = PaymentElement.objects.filter(invoice=invoice).aggregate(total=Sum("value"))["total"] or 0
            if total_payed >= invoice.value:
                return redirect("payment", payment_id=0, person_id=person.id, invoice_id=invoice.id)

            remaining = invoice.value - total_payed
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
                currency=invoice.currency if invoice else "EUR",
                is_recurrent=is_recurrent,
                value=remaining
            )
            PaymentElement.objects.create(payment=payment, invoice=invoice, value=remaining)
            update_invoice_payed(invoice)
            new = False  # IMPORTANT

        else:
            old_type = payment.type
            old_serial = payment.serial
            old_number = payment.number

            payment.description = desc
            payment.type = p_type
            payment.payment_date = payment_date
            payment.modified_by = request.user
            payment.modified_at = date_now

            if old_type == "cash" and p_type == "bank" and old_serial and old_number:
                # Dacă e ultima plată de tip cash, corectează serialul
                last_payment = Payment.objects.filter(type="cash", is_client=is_client).order_by("-id").first()
                if last_payment and last_payment.id == payment.id:
                    serials.receipt_number = max(1, serials.receipt_number - 1)
                    serials.save()
                payment.serial = ""
                payment.number = ""

            elif old_type == "bank" and p_type == "cash" and not payment.serial:
                serial, number = get_serial_and_number(is_client, p_type, serials, assign=True)
                payment.serial = serial
                payment.number = number

            payment.save()

        # Scoatere element
        if "payment_element_id" in form:
            try:
                elem_id = int(form["payment_element_id"])
                if PaymentElement.objects.filter(payment=payment).count() > 1:
                    PaymentElement.objects.get(id=elem_id).delete()
            except:
                pass

        # Adăugare factură neachitată
        if "unpayed_element_id" in form:
            try:
                inv = Invoice.objects.get(id=int(form["unpayed_element_id"]))
                total_payed = PaymentElement.objects.filter(invoice=inv).aggregate(total=Sum("value"))["total"] or 0
                if total_payed < inv.value and not PaymentElement.objects.filter(payment=payment, invoice=inv).exists():
                    PaymentElement.objects.get_or_create(payment=payment, invoice=inv)
                    update_invoice_payed(inv)
            except Invoice.DoesNotExist:
                pass

        # Setare valoare
        if "payment_value" in form and payment:
            try:
                val = Decimal(form.get("payment_value"))
                if val > 0 and PaymentElement.objects.filter(payment=payment).count() < 2:
                    set_payment_value(payment, val)
            except:
                pass
        else:
            set_payment_value(payment)

        if payment and payment.id:
            return redirect("payment", payment_id=payment.id, person_id=person.id, invoice_id=invoice.id if invoice else 0)
        else:
            return redirect("payment", payment_id=0, person_id=person.id, invoice_id=invoice.id if invoice else 0)

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
    payment = get_object_or_404(Payment, id=payment_id)
    payment_elements = PaymentElement.objects.filter(payment=payment).order_by("id")
    leading_number = payment.number.rjust(4,'0')

    # Open the logo image
    with open('static/images/logo-se.jpeg', 'rb') as f:
        svg_content = f.read()
    # Encode the image în base64
    logo_base64 = base64.b64encode(svg_content).decode('utf-8')
    # Open the CSS content
    with open('static/css/invoice.css', 'rb') as f:
        invoice_content = f.read()

    context = {
        "payment": payment,
        "leading_number": leading_number,
        "payment_elements": payment_elements,
        "logo_base64": logo_base64,
        "value_in_words": num2words(payment.value, lang='de').capitalize()
    }
    html_content = render_to_string("payments/print_receipt.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=invoice_content)])
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=Beleg-{payment.serial}-{payment.number}.pdf'
    return response

@login_required(login_url="/login/")
def print_cancellation_receipt(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    payment_elements = PaymentElement.objects.filter(payment=payment).order_by("id")
    leading_number = payment.number.rjust(4,'0')

    # Open the logo image
    with open('static/images/logo-se.jpeg', 'rb') as f:
        svg_content = f.read()
    # Encode the image în base64
    logo_base64 = base64.b64encode(svg_content).decode('utf-8')
    # Open the CSS content
    with open('static/css/invoice.css', 'rb') as f:
        invoice_content = f.read()

    context = {
        "payment": payment,
        "leading_number": leading_number,
        "payment_elements": payment_elements,
        "logo_base64": logo_base64,
        "value_in_words": num2words(payment.value, lang='de').capitalize()
    }
    html_content = render_to_string("payments/print_cancellation_receipt.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=invoice_content)])
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=Stornobeleg-{payment.serial}-{payment.number}.pdf'
    return response