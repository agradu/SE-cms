from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
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
    # Default parts
    payment_elements = []
    unpayed_elements = []
    date_now = timezone.now()
    person = get_object_or_404(Person, id=person_id)
    serials = Serial.objects.get(id=1)
    payment_value = 0
    is_recurrent = False
    if invoice_id > 0:
        invoice = get_object_or_404(Invoice, id=invoice_id)
        is_client = invoice.is_client
    else:
        invoice = ""
    if payment_id > 0:
        payment = get_object_or_404(Payment, id=payment_id)
        is_client = payment.is_client
        new = False
    else:
        payment =""
        new = True
        if is_client == False:
            receipt_serial = ""
            receipt_number = ""
    all_invoices = Invoice.objects.filter(person=person).order_by("id")
    payed_elements = PaymentElement.objects.filter(payment__person=person).order_by("id")
    unpayed_elements = all_invoices.exclude(
            id__in=payed_elements.values_list('invoice__id', flat=True)
        ).filter(is_client=is_client)
    
    def set_value(payment, value=0):
        payment_elements = PaymentElement.objects.filter(payment=payment).order_by('invoice__created_at')
        
        total_invoice_value = sum(e.invoice.value for e in payment_elements)
        invoices_to_update = set()
        
        # Dacă e o singură factură și se permite plată parțială
        if len(payment_elements) == 1 and 0 < abs(value) < abs(total_invoice_value):
            element = payment_elements.first()
            element.value = value if value > 0 else -abs(value)
            element.save()
            payment.value = element.value
            invoices_to_update.add(element.invoice)
        else:
            total_payment_value = 0
            for element in payment_elements:
                invoice_value = element.invoice.value
                element.value = invoice_value
                element.save()
                total_payment_value += invoice_value
                invoices_to_update.add(element.invoice)
            payment.value = total_payment_value

        payment.save()

        # Actualizează suma plătită pe fiecare factură
        for invoice in invoices_to_update:
            invoice.payed = PaymentElement.objects.filter(invoice=invoice).aggregate(
                total=Sum("value")
            )["total"] or 0
            invoice.save()
            
    if payment_id > 0:  # if payment exists
        receipt_serial = payment.serial
        receipt_number = payment.number
        payment_elements = PaymentElement.objects.filter(payment=payment).order_by('invoice__created_at')
        if request.method == "POST":
            if "payment_description" in request.POST:
                payment.description = request.POST.get("payment_description")
                payment.type = request.POST.get("payment_type")
                if payment.is_client and payment.type == "cash":
                    receipt_serial = serials.receipt_serial
                    receipt_number = serials.receipt_number-1
                    if receipt_number < 1:
                        receipt_number = 1
                elif payment.is_client and payment.type == "bank":
                    receipt_serial = ""
                    receipt_number = ""
                else:
                    receipt_serial = request.POST.get("receipt_serial")
                    receipt_number = request.POST.get("receipt_number")
                    if receipt_serial == None:
                        receipt_serial = payment.serial
                    if receipt_number == None:
                        receipt_number = payment.number
                payment.serial = receipt_serial
                payment.number = receipt_number
                payment_date = request.POST.get("payment_date")
                try:
                    payment_date_naive = datetime.strptime(f"{payment_date}", "%Y-%m-%d")
                    payment.payment_date = timezone.make_aware(payment_date_naive)
                except:
                    payment.payment_date = date_now
            if "payment_element_id" in request.POST:
                payment_element_id = int(request.POST.get("payment_element_id"))
                try: # delete an element
                    element = PaymentElement.objects.get(id=payment_element_id)
                    if PaymentElement.objects.filter(payment=payment).count() > 1:
                        element.delete()
                        # Save the payment value
                        set_value(payment, payment_value)
                except:
                    print("Element",payment_element_id,"is missing!")
            if "unpayed_element_id" in request.POST:
                unpayed_element_id = int(request.POST.get("unpayed_element_id"))
                try: # add an element
                    element = unpayed_elements.get(id=unpayed_element_id)
                    PaymentElement.objects.get_or_create(
                        payment = payment,
                        invoice = element
                    )
                    # Save the payment value
                    set_value(payment, payment_value)
                except:
                    print("Element",unpayed_element_id,"is missing!")    
            if "payment_value" in request.POST:
                payment_value = Decimal(request.POST.get("payment_value"))
                # Save the payment value
                set_value(payment, payment_value)

            # Setting the modiffied user and date
            payment.modified_by = request.user
            payment.modified_at = date_now
            # Save the payment infos
            payment.save()

    else:  # if payment is new
        receipt_serial = ""
        receipt_number = ""
        invoice_value = invoice.value
        if request.method == "POST":
            if "payment_description" in request.POST:
                payment_description = request.POST.get("payment_description")
                payment_type = request.POST.get("payment_type")
                if invoice.is_client and payment_type == "cash":
                    receipt_serial = serials.receipt_serial
                    receipt_number = serials.receipt_number
                    serials.receipt_number += 1
                    serials.save() 
                else:
                    receipt_serial = request.POST.get("receipt_serial")
                    receipt_number = request.POST.get("receipt_number")
                    if receipt_serial == None:
                        receipt_serial = ""
                    if receipt_number == None:
                        receipt_number = ""  
                payment_date = request.POST.get("payment_date")
                try:
                    payment_date_naive = datetime.strptime(f"{payment_date}", "%Y-%m-%d")
                    payment_date = timezone.make_aware(payment_date_naive)
                except:
                    payment_date = date_now
                payment = Payment(
                    description = payment_description,
                    type = payment_type,
                    serial = receipt_serial,
                    number = receipt_number,
                    person = person,
                    payment_date = payment_date,
                    is_client = invoice.is_client,
                    modified_by = request.user,
                    created_by = request.user,
                    currency = invoice.currency,
                    is_recurrent = is_recurrent,
                )
                payment.save()
                # Add all unpayed elements to this payment
                for element in unpayed_elements:
                    PaymentElement.objects.get_or_create(
                        payment=payment,
                        invoice=invoice
                    )
                # Save the payment value
                set_value(payment)

                # Add the partial payed element if it exists
                invoice_payment_elements = PaymentElement.objects.filter(invoice=invoice)
                print("invoice_payment_elements:",invoice_payment_elements)
                already_paid = 0
                for element in invoice_payment_elements:
                    already_paid += element.payment.value
                rest_value = invoice.value - already_paid
                if rest_value > 0:
                    PaymentElement.objects.get_or_create(
                        payment=payment,
                        invoice=invoice
                    )
                # Save the payment value
                set_value(payment, rest_value)
                
                new = False
                return redirect(
                    "payment",
                    payment_id = payment.id,
                    invoice_id = invoice.id,
                    person_id = person.id,
                )
    return render(
        request,
        "payments/payment.html",
        {
            "person": person,
            "payment": payment,
            "receipt_serial": receipt_serial,
            "receipt_number": receipt_number,
            "is_client": is_client,
            "payment_elements": payment_elements,
            "unpayed_elements": unpayed_elements,
            "new": new
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