from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from orders.models import Order, OrderElement
from persons.models import Person
from payments.models import PaymentInvoice
from .models import Invoice, InvoiceElement
from services.models import Serial
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils import timezone
from weasyprint import HTML, CSS
import base64

# Create your views here.


@login_required(login_url="/login/")
def invoices(request):
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
    # CLIENT/PROVIDER INVOICES
    selected_invoices = Invoice.objects.filter(
        Q(person__firstname__icontains=search)
        | Q(person__lastname__icontains=search)
        | Q(person__company_name__icontains=search)
    ).filter(created_at__gte=filter_start, created_at__lte=filter_end)
    person_invoices = []
    for i in selected_invoices:
        invoice_elements = InvoiceElement.objects.filter(invoice=i).order_by("id")
        i_orders = []
        for e in invoice_elements:
            if e.element.order not in i_orders:
                i_orders.append(e.element.order)
        i_payed = 0
        i_payments = PaymentInvoice.objects.filter(invoice=i)
        for p in i_payments:
            i_payed += p.payment.value
        if i.value > 0:
            payed = int(i_payed / i.value * 100)
        else:
            payed = 0
        person_invoices.append(
            {"invoice": i, "payed": payed, "value": i.value, "orders": i_orders}
        )
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    if sort == "type":
        person_invoices = sorted(
            person_invoices, key=lambda x: x["invoice"].is_client, reverse=True
        )
    elif sort == "invoice":
        person_invoices = sorted(
            person_invoices, key=lambda x: x["invoice"].id, reverse=True
        )
    elif sort == "person":
        person_invoices = sorted(
            person_invoices, key=lambda x: x["invoice"].person.firstname
        )
    elif sort == "assignee":
        person_invoices = sorted(
            person_invoices, key=lambda x: x["invoice"].modified_by.first_name
        )
    elif sort == "registered":
        person_invoices = sorted(
            person_invoices, key=lambda x: x["invoice"].created_at, reverse=True
        )
    elif sort == "deadline":
        person_invoices = sorted(
            person_invoices, key=lambda x: x["invoice"].deadline, reverse=True
        )
    elif sort == "status":
        person_invoices = sorted(person_invoices, key=lambda x: x["invoice"].status.id)
    elif sort == "value":
        person_invoices = sorted(
            person_invoices, key=lambda x: x["value"], reverse=True
        )
    elif sort == "payed":
        person_invoices = sorted(person_invoices, key=lambda x: x["payed"])
    elif sort == "update":
        person_invoices = sorted(
            person_invoices, key=lambda x: x["invoice"].modified_at, reverse=True
        )
    else:
        person_invoices = sorted(
            person_invoices, key=lambda x: x["invoice"].created_at, reverse=True
        )

    paginator = Paginator(person_invoices, 10)
    invoices_on_page = paginator.get_page(page)

    return render(
        request,
        "payments/invoices.html",
        {
            "person_invoices": invoices_on_page,
            "sort": sort,
            "search": search,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )


@login_required(login_url="/login/")
def invoice(request, invoice_id, person_id, order_id):
    # Default parts
    invoice_elements = []
    uninvoiced_elements = []
    date_now = timezone.now()
    person = get_object_or_404(Person, id=person_id)
    serials = Serial.objects.get(id='1')
    invoice_serial = serials.invoice_serial
    invoice_number = serials.invoice_number
    if order_id > 0:
        order = get_object_or_404(Order, id=order_id)
        is_client = order.is_client
    else:
        order = ""
    if invoice_id > 0:
        invoice = get_object_or_404(Invoice, id=invoice_id)
        is_client = invoice.is_client
        new = False
    else:
        invoice =""
        new = True
    all_orders_elements = OrderElement.objects.exclude(status__id='6').filter(order__person=person).order_by("id")
    invoiced_elements = InvoiceElement.objects.exclude(element__status__id='6').filter(invoice__person=person).order_by("id")
    uninvoiced_elements = all_orders_elements.exclude(id__in=invoiced_elements.values_list('element__id', flat=True))      
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
                    invoice.serial = request.POST.get("invoice_serial")
                    invoice.number = request.POST.get("invoice_number")
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

@login_required(login_url="/login/")
def print_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    invoice_elements = InvoiceElement.objects.exclude(element__status__id='6').filter(invoice=invoice).order_by("id")
    date1 = invoice.created_at.date()
    date2 = invoice.deadline
    day_left = (date2 - date1).days
    leading_number = invoice.number.rjust(3,'0')

    # Open the logo image
    with open('static/images/logo-se.jpeg', 'rb') as f:
        svg_content = f.read()
    # Encode the image în base64
    logo_base64 = base64.b64encode(svg_content).decode('utf-8')
    # Open the CSS content
    with open('static/css/invoice.css', 'rb') as f:
        invoice_content = f.read()

    context = {
        "invoice": invoice,
        "day_left": day_left,
        "leading_number": leading_number,
        "invoice_elements": invoice_elements,
        "logo_base64": logo_base64
    }
    html_content = render_to_string("payments/print_invoice.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=invoice_content)])
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=invoice-{invoice.serial}-{invoice.number}.pdf'
    return response