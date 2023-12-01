from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from persons.models import Person
from orders.models import Order, OrderElement
from invoices.models import Invoice, InvoiceElement
from payments.models import Payment, PaymentElement
from services.models import Currency, Status, Service, UM, Serial
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils import timezone
from weasyprint import HTML, CSS
import base64

# Create your views here.


@login_required(login_url="/login/")
def payments(request):
    # search elements
    search = ""
    date_now = timezone.now().replace(hour=23, minute=59, second=59, microsecond=0)
    date_before = date_now - timedelta(days=10)
    reg_start = date_before.strftime("%Y-%m-%d")
    filter_start = date_before
    reg_end = date_now.strftime("%Y-%m-%d")
    filter_end = date_now
    if request.method == "POST":
        search = request.POST.get("search")
        if len(search) > 2:
            reg_start = request.POST.get("reg_start")
            filter_start = datetime.strptime(reg_start, "%Y-%m-%d")
            filter_start = timezone.make_aware(filter_start)
            reg_end = request.POST.get("reg_end")
            filter_end = datetime.strptime(reg_end, "%Y-%m-%d")
            filter_end = timezone.make_aware(filter_end).replace(
                hour=23, minute=59, second=59, microsecond=0
            )
        else:
            search = ""
    # CLIENT/PROVIDER PAYMENTS
    selected_payments = Payment.objects.filter(
        Q(person__firstname__icontains=search)
        | Q(person__lastname__icontains=search)
        | Q(person__company_name__icontains=search)
    ).filter(created_at__gte=filter_start, created_at__lte=filter_end)
    person_payments = []
    for p in selected_payments:
        invoices = PaymentElement.objects.filter(payment=p)
        person_payments.append({"payment": p, "payed": p.value, "invoices":invoices})
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    def get_sort_key(x):
        if sort == "type":
            return x["payment"].type
        elif sort == "payment":
            return x["payment"].id
        elif sort == "person":
            return x["payment"].person.firstname
        elif sort == "receipt":
            return (x["payment"].serial, x["payment"].number)
        elif sort == "assignee":
            return x["payment"].modified_by.first_name
        elif sort == "registered":
            return x["payment"].created_at
        elif sort == "value":
            return x["payment"].value
        elif sort == "update":
            return x["payment"].modified_at
        else:
            return x["payment"].created_at
    person_payments = sorted(person_payments, key=get_sort_key, reverse=(sort != "person"))

    paginator = Paginator(person_payments, 10)
    payments_on_page = paginator.get_page(page)

    return render(
        request,
        "payments/payments.html",
        {
            "person_payments": payments_on_page,
            "sort": sort,
            "search": search,
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
    payment_serial = serials.receipt_serial
    payment_number = serials.receipt_number
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
            payment_serial = ""
            payment_number = ""
    all_invoice_elements = InvoiceElement.objects.filter(invoice__person=person).order_by("id")
    payment_elements = PaymentElement.objects.filter(payment__person=person).order_by("id")
    unpayed_elements = all_invoice_elements.exclude(id__in=payment_elements.values_list('invoice__id', flat=True))      
    def set_value(invoice): # calculate and save the value of the invoice
        invoice_elements = InvoiceElement.objects.filter(invoice=invoice).order_by("id")
        invoice.value = 0
        for e in invoice_elements:
            invoice.value += (e.element.price * e.element.quantity)
        invoice.save()
    if invoice_id > 0:  # if invoice exists
        invoice_serial = invoice.serial
        invoice_number = invoice.number
        invoice_elements = InvoiceElement.objects.exclude(element__status__id='6').filter(invoice=invoice).order_by('element__order__created_at')
        if request.method == "POST":
            if "invoice_description" in request.POST:
                invoice.description = request.POST.get("invoice_description")
                if invoice.is_client == False:
                    invoice.serial = request.POST.get("invoice_serial").upper()
                    invoice_serial =invoice.serial
                    invoice.number = request.POST.get("invoice_number").upper()
                    invoice_number = invoice.number
                deadline_date = request.POST.get("deadline_date")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date}", "%Y-%m-%d")
                    invoice.deadline = timezone.make_aware(deadline_naive)
                except:
                    invoice.deadline = date_now  
            if "invoice_element_id" in request.POST:
                invoice_element_id = int(request.POST.get("invoice_element_id"))
                try: # delete an element
                    element = InvoiceElement.objects.get(id=invoice_element_id)
                    if InvoiceElement.objects.filter(invoice=invoice).count() > 1:
                        element.delete()
                except:
                    print("Element",invoice_element_id,"is missing!")
            if "uninvoiced_element_id" in request.POST:
                uninvoiced_element_id = int(request.POST.get("uninvoiced_element_id"))
                try: # add an element
                    element = uninvoiced_elements.get(id=uninvoiced_element_id)
                    InvoiceElement.objects.get_or_create(
                        invoice=invoice,
                        element=element
                    )
                except:
                    print("Element",uninvoiced_element_id,"is missing!")
            # Setting the modiffied user and date
            invoice.modified_by = request.user
            invoice.modified_at = date_now
            # Save the invoice value
            set_value(invoice)

    else:  # if invoice is new
        if request.method == "POST":
            if "invoice_description" in request.POST:
                invoice_description = request.POST.get("invoice_description")
                if order.is_client == False:
                    invoice_serial = request.POST.get("invoice_serial")
                    invoice_number = request.POST.get("invoice_number")
                    if invoice_serial =="" and invoice_number =="":
                        invoice_serial = "??"
                        invoice_serial = "???"
                    
                deadline_date = request.POST.get("deadline_date")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date}", "%Y-%m-%d")
                    invoice_deadline = timezone.make_aware(deadline_naive)
                except:
                    invoice_deadline = date_now
                invoice = Invoice(
                    description = invoice_description,
                    serial = invoice_serial,
                    number = invoice_number,
                    person = person,
                    deadline = invoice_deadline,
                    is_client = order.is_client,
                    modified_by = request.user,
                    created_by = request.user,
                    currency = order.currency,
                )
                invoice.save()
                # Add all uninvoiced elements to this invoice
                for element in uninvoiced_elements:
                    InvoiceElement.objects.get_or_create(
                        invoice=invoice,
                        element=element
                    )
                # Save the invoice value
                set_value(invoice)
                new = False
                serials.invoice_number += 1
                serials.save()
                return redirect(
                    "invoice",
                    invoice_id = invoice.id,
                    order_id = order.id,
                    person_id = person.id,
                )
        print(is_client)
    return render(
        request,
        "payments/invoice.html",
        {
            "person": person,
            "invoice": invoice,
            "invoice_serial": invoice_serial,
            "invoice_number": invoice_number,
            "is_client": is_client,
            "invoice_elements": invoice_elements,
            "uninvoiced_elements": uninvoiced_elements,
            "new": new
        },
    )