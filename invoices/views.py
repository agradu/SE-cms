from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from orders.models import Order, OrderElement
from persons.models import Person
from payments.models import Payment, PaymentElement
from .models import Invoice, InvoiceElement, Proforma, ProformaElement
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
    date_now = timezone.now().replace(hour=23, minute=59, second=59, microsecond=0)
    date_before = (date_now - timedelta(days=360)).replace(hour=0, minute=0, second=0, microsecond=0)
    reg_start = date_before.strftime("%Y-%m-%d")
    filter_start = date_before
    reg_end = date_now.strftime("%Y-%m-%d")
    filter_end = date_now
    if request.method == "POST":
        search_client = request.POST.get("search_client")
        search_description = request.POST.get("search_description")
        if len(search_client) > 2 or len(search_description) > 2:
            reg_start = request.POST.get("reg_start")
            filter_start = datetime.strptime(reg_start, "%Y-%m-%d")
            filter_start = timezone.make_aware(filter_start)
            reg_end = request.POST.get("reg_end")
            filter_end = datetime.strptime(reg_end, "%Y-%m-%d")
            filter_end = timezone.make_aware(filter_end).replace(
                hour=23, minute=59, second=59, microsecond=0
            )
    else:
        search_client = ""
        search_description = ""
    # CLIENT/PROVIDER INVOICES
    selected_invoices = (
        Invoice.objects.filter(
        Q(person__firstname__icontains=search_client)
        | Q(person__lastname__icontains=search_client)
        | Q(person__company_name__icontains=search_client)
        )
        .filter(description__icontains=search_description)
        .filter(created_at__gte=filter_start, created_at__lte=filter_end)
    )
    person_invoices = []
    for i in selected_invoices:
        invoice_elements = InvoiceElement.objects.filter(invoice=i).order_by("id")
        i_orders = []
        for e in invoice_elements:
            if e.element.order not in i_orders:
                i_orders.append(e.element.order)
        i_payed = 0
        i_payments = PaymentElement.objects.filter(invoice=i)
        for p in i_payments:
            if p.payment.value < p.invoice.value:
                i_payed += p.payment.value
            else:
                i_payed += p.invoice.value
        if i.value != 0:
            payed = int(i_payed / i.value * 100)
        else:
            payed = 0
        try:
            proforma = Proforma.objects.get(invoice=i)
        except Proforma.DoesNotExist:
            proforma = None
        person_invoices.append(
            {"invoice": i, "payed": payed, "value": i.value, "orders": i_orders, "proforma": proforma}
        )
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    def get_sort_key(x):
        if sort == "type":
            return x["invoice"].is_client
        elif sort == "invoice":
            return (x["invoice"].serial, x["invoice"].number)
        elif sort == "person":
            return x["invoice"].person.firstname
        elif sort == "assignee":
            return x["invoice"].modified_by.first_name
        elif sort == "registered":
            return x["invoice"].created_at
        elif sort == "deadline":
            return x["invoice"].deadline
        elif sort == "status":
            return x["invoice"].status.id
        elif sort == "value":
            return x["value"]
        elif sort == "payed":
            return x["payed"]
        elif sort == "update":
            return x["invoice"].modified_at
        else:
            return x["invoice"].created_at
    person_invoices = sorted(person_invoices, key=get_sort_key, reverse=(sort != "person" and sort != "payed"))

    paginator = Paginator(person_invoices, 10)
    invoices_on_page = paginator.get_page(page)

    return render(
        request,
        "payments/invoices.html",
        {
            "person_invoices": invoices_on_page,
            "sort": sort,
            "search_client": search_client,
            "search_description": search_description,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )

@login_required(login_url="/login/")
def cancellation_invoice(request, invoice_id):
    # Default parts
    cancelled_invoice = get_object_or_404(Invoice, id=invoice_id)
    invoice_elements = InvoiceElement.objects.filter(invoice=cancelled_invoice).order_by("id")
    serials = Serial.objects.get(id=1)
    
    cancellation_invoice = Invoice(
        serial = serials.invoice_serial,
        number = serials.invoice_number,
        person = cancelled_invoice.person,
        is_client = cancelled_invoice.is_client,
        modified_by = request.user,
        created_by = request.user,
        currency = cancelled_invoice.currency,
        cancellation_to = cancelled_invoice,
        value = 0 - cancelled_invoice.value,
        description = "Cancellation invoice"
    )
    cancellation_invoice.save()

    cancelled_invoice.cancelled_from = cancellation_invoice
    cancelled_invoice.save()

    test_payment = PaymentElement.objects.filter(invoice=cancelled_invoice)
    p_value = 0
    for p in test_payment:
        p_value += p.payment.value

    cancelled_payment = Payment(
        person = cancelled_invoice.person,
        is_client = cancelled_invoice.is_client,
        modified_by = request.user,
        created_by = request.user,
        currency = cancelled_invoice.currency,
        value = cancelled_invoice.value - p_value,
        description = "Cancelled payment"
    )
    cancelled_payment.save()

    cancellation_payment = Payment(
        person = cancellation_invoice.person,
        is_client = cancellation_invoice.is_client,
        modified_by = request.user,
        created_by = request.user,
        currency = cancellation_invoice.currency,
        value = cancellation_invoice.value + p_value,
        description = "Cancellation payment"
    )
    cancellation_payment.save()

    cancelled_payment_element = PaymentElement(
        payment = cancelled_payment,
        invoice = cancelled_invoice
    )
    cancelled_payment_element.save()

    cancellation_payment_element = PaymentElement(
        payment = cancellation_payment,
        invoice = cancellation_invoice
    )
    cancellation_payment_element.save()
    
    serials.invoice_number += 1
    serials.save()
    for element in invoice_elements:
        c_element = InvoiceElement(
            invoice = cancellation_invoice,
            element = element.element
        )
        c_element.save()
    return redirect(
        "invoices",
    )

@login_required(login_url="/login/")
def invoice(request, invoice_id, person_id, order_id):
    # Default parts
    invoice_elements = []
    uninvoiced_elements = []
    date_now = timezone.localtime()
    clock = date_now.time()
    person = get_object_or_404(Person, id=person_id)
    serials = Serial.objects.get(id=1)
    invoice_serial = serials.invoice_serial
    invoice_number = serials.invoice_number
    if order_id > 0:
        order = get_object_or_404(Order, id=order_id)
        is_client = order.is_client
    else:
        order = ""
    if invoice_id > 0:
        invoice = get_object_or_404(Invoice, id=invoice_id)
        invoice_date = invoice.created_at
        is_client = invoice.is_client
        new = False
    else:
        invoice =""
        new = True
        if is_client == False:
            invoice_serial = ""
            invoice_number = ""
    all_orders_elements = OrderElement.objects.exclude(status__id='0').filter(order__person=person).order_by("id")
    invoiced_elements = InvoiceElement.objects.exclude(element__status__id='0').filter(invoice__person=person).order_by("id")
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
        invoice_elements = InvoiceElement.objects.exclude(element__status__id='0').filter(invoice=invoice).order_by('element__order__created_at')
        if request.method == "POST":
            if "invoice_description" in request.POST:
                invoice.description = request.POST.get("invoice_description")
                if invoice.is_client == False:
                    i_serial = request.POST.get("invoice_serial")
                    if i_serial != None:
                        invoice.serial = i_serial.upper()
                    invoice_serial = invoice.serial
                    i_number = request.POST.get("invoice_number")
                    if i_number != None:
                        invoice.number = i_number.upper()
                    invoice_number = invoice.number
                deadline_date = request.POST.get("deadline_date")
                invoice_date = request.POST.get("invoice_date")
                try:
                    invoice_deadline = datetime.strptime(deadline_date, "%Y-%m-%d").date()
                    new_invoice_date = datetime.combine(datetime.strptime(invoice_date, "%Y-%m-%d").date(), clock)
                    if not invoice.created_at == new_invoice_date:
                        invoice_date = new_invoice_date
                except:
                    invoice_deadline = date_now.date()
                invoice.created_at = invoice_date
                invoice.deadline = invoice_deadline
                    
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
                    if invoice_serial == "" and invoice_number == "":
                        invoice_serial = "??"
                        invoice_number = "???"
                else:
                    serials.invoice_number += 1
                    serials.save()
                
                
                deadline_date = request.POST.get("deadline_date")
                invoice_date = request.POST.get("invoice_date")
                try:
                    invoice_deadline = datetime.strptime(deadline_date, "%Y-%m-%d").date()
                    new_invoice_date = datetime.combine(datetime.strptime(invoice_date, "%Y-%m-%d").date(), clock)
                    if not date_now == new_invoice_date:
                        invoice_date = new_invoice_date
                except:
                    invoice_deadline = date_now.date()
                    invoice_date = date_now
                invoice = Invoice(
                    created_at = invoice_date,
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
    leading_invoice = invoice.number.rjust(3,'0')
    try:
        proforma = Proforma.objects.get(invoice=invoice)
        proforma_number = proforma.number
    except:
        proforma = ""
        proforma_number = ""
    leading_proforma = proforma_number.rjust(3,'0')

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
        "proforma": proforma,
        "day_left": day_left,
        "leading_invoice": leading_invoice,
        "leading_proforma": leading_proforma,
        "invoice_elements": invoice_elements,
        "logo_base64": logo_base64
    }
    html_content = render_to_string("payments/print_invoice.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=invoice_content)])
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=invoice-{invoice.serial}-{invoice.number}.pdf'
    return response

@login_required(login_url="/login/")
def proformas(request):
    # search elements
    search = request.GET.get("search")
    if search == None:
        search = ""
    date_now = timezone.now().replace(hour=23, minute=59, second=59, microsecond=0)
    date_before = (date_now - timedelta(days=360)).replace(hour=0, minute=0, second=0, microsecond=0)
    reg_start = date_before.strftime("%Y-%m-%d")
    filter_start = date_before
    reg_end = date_now.strftime("%Y-%m-%d")
    filter_end = date_now
    if request.method == "POST":
        search_client = request.POST.get("search_client")
        search_description = request.POST.get("search_description")
        if len(search_client) > 2 or len(search_description) > 2:
            reg_start = request.POST.get("reg_start")
            filter_start = datetime.strptime(reg_start, "%Y-%m-%d")
            filter_start = timezone.make_aware(filter_start)
            reg_end = request.POST.get("reg_end")
            filter_end = datetime.strptime(reg_end, "%Y-%m-%d")
            filter_end = timezone.make_aware(filter_end).replace(
                hour=23, minute=59, second=59, microsecond=0
            )
    else:
        search_client = ""
        search_description = ""
    # CLIENT/PROVIDER PROFORMAS
    selected_proformas = (
        Proforma.objects.filter(
        Q(person__firstname__icontains=search_client)
        | Q(person__lastname__icontains=search_client)
        | Q(person__company_name__icontains=search_client)
        )
        .filter(description__icontains=search_description)
        .filter(created_at__gte=filter_start, created_at__lte=filter_end)
    )
    person_proformas = []
    for p in selected_proformas:
        proforma_elements = ProformaElement.objects.filter(proforma=p).order_by("id")
        p_orders = []
        for e in proforma_elements:
            if e.element.order not in p_orders:
                p_orders.append(e.element.order)
        person_proformas.append(
            {"proforma": p, "value": p.value, "orders": p_orders}
        )
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    def get_sort_key(x):
        if sort == "proforma":
            return (x["proforma"].serial, x["proforma"].number)
        elif sort == "person":
            return x["proforma"].person.firstname
        elif sort == "assignee":
            return x["proforma"].modified_by.first_name
        elif sort == "registered":
            return x["proforma"].created_at
        elif sort == "deadline":
            return x["proforma"].deadline
        elif sort == "status":
            return x["proforma"].status.id
        elif sort == "value":
            return x["value"]
        elif sort == "update":
            return x["proforma"].modified_at
        else:
            return x["proforma"].created_at
    person_proformas = sorted(person_proformas, key=get_sort_key, reverse=(sort != "person" and sort != "payed"))

    paginator = Paginator(person_proformas, 10)
    proformas_on_page = paginator.get_page(page)

    return render(
        request,
        "payments/proformas.html",
        {
            "person_proformas": proformas_on_page,
            "sort": sort,
            "search_client": search_client,
            "search_description": search_description,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )

@login_required(login_url="/login/")
def proforma(request, proforma_id, person_id, order_id):
    # Default parts
    proforma_elements = []
    unproformed_elements = []
    date_now = timezone.now()
    person = get_object_or_404(Person, id=person_id)
    serials = Serial.objects.get(id=1)
    proforma_serial = serials.proforma_serial
    proforma_number = serials.proforma_number
    if order_id > 0:
        order = get_object_or_404(Order, id=order_id)
    else:
        order = ""
    if proforma_id > 0:
        proforma = get_object_or_404(Proforma, id=proforma_id)
        new = False
    else:
        proforma =""
        new = True
    all_orders_elements = OrderElement.objects.exclude(status__id='6').exclude(order__is_client=False).filter(order__person=person).order_by("id")
    proformed_elements = ProformaElement.objects.exclude(element__status__id='6').filter(proforma__person=person).order_by("id")
    unproformed_elements = all_orders_elements.exclude(id__in=proformed_elements.values_list('element__id', flat=True))
    def set_value(proforma): # calculate and save the value of the proforma
        proforma_elements = ProformaElement.objects.filter(proforma=proforma).order_by("id")
        proforma.value = 0
        for e in proforma_elements:
            proforma.value += (e.element.price * e.element.quantity)
        proforma.save()
    if proforma_id > 0:  # if proforma exists
        proforma_serial = proforma.serial
        proforma_number = proforma.number
        proforma_elements = ProformaElement.objects.exclude(element__status__id='6').filter(proforma=proforma).order_by('element__order__created_at')
        if request.method == "POST":
            if "proforma_description" in request.POST:
                proforma.description = request.POST.get("proforma_description")
                deadline_date = request.POST.get("deadline_date")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date}", "%Y-%m-%d")
                    proforma.deadline = timezone.make_aware(deadline_naive)
                except:
                    proforma.deadline = date_now  
            if "proforma_element_id" in request.POST:
                proforma_element_id = int(request.POST.get("proforma_element_id"))
                try: # delete an element
                    element = ProformaElement.objects.get(id=proforma_element_id)
                    if ProformaElement.objects.filter(proforma=proforma).count() > 1:
                        element.delete()
                except:
                    print("Element",proforma_element_id,"is missing!")
            if "unproformed_element_id" in request.POST:
                unproformed_element_id = int(request.POST.get("unproformed_element_id"))
                try: # add an element
                    element = unproformed_elements.get(id=unproformed_element_id)
                    ProformaElement.objects.get_or_create(
                        proforma=proforma,
                        element=element
                    )
                except:
                    print("Element",unproformed_element_id,"is missing!")
            # Setting the modiffied user and date
            proforma.modified_by = request.user
            proforma.modified_at = date_now
            # Save the proforma value
            set_value(proforma)

    else:  # if proforma is new
        if request.method == "POST":
            if "proforma_description" in request.POST:
                proforma_description = request.POST.get("proforma_description")     
                deadline_date = request.POST.get("deadline_date")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date}", "%Y-%m-%d")
                    proforma_deadline = timezone.make_aware(deadline_naive)
                except:
                    proforma_deadline = date_now
                proforma = Proforma(
                    description = proforma_description,
                    serial = proforma_serial,
                    number = proforma_number,
                    person = person,
                    deadline = proforma_deadline,
                    is_client = order.is_client,
                    modified_by = request.user,
                    created_by = request.user,
                    currency = order.currency,
                )
                proforma.save()
                # Add all unproformed elements to this proforma
                for element in unproformed_elements:
                    ProformaElement.objects.get_or_create(
                        proforma=proforma,
                        element=element
                    )
                # Save the proforma value
                set_value(proforma)
                new = False
                serials.proforma_number += 1
                serials.save()
                return redirect(
                    "proforma",
                    proforma_id = proforma.id,
                    order_id = order.id,
                    person_id = person.id,
                )
    return render(
        request,
        "payments/proforma.html",
        {
            "person": person,
            "proforma": proforma,
            "proforma_serial": proforma_serial,
            "proforma_number": proforma_number,
            "proforma_elements": proforma_elements,
            "unproformed_elements": unproformed_elements,
            "new": new
        },
    )

@login_required(login_url="/login/")
def print_proforma(request, proforma_id):
    proforma = get_object_or_404(Proforma, id=proforma_id)
    proforma_elements = ProformaElement.objects.exclude(element__status__id='6').filter(proforma=proforma).order_by("id")
    date1 = proforma.created_at.date()
    date2 = proforma.deadline
    day_left = (date2 - date1).days
    leading_number = proforma.number.rjust(3,'0')

    # Open the logo image
    with open('static/images/logo-se.jpeg', 'rb') as f:
        svg_content = f.read()
    # Encode the image în base64
    logo_base64 = base64.b64encode(svg_content).decode('utf-8')
    # Open the CSS content
    with open('static/css/invoice.css', 'rb') as f:
        proforma_content = f.read()

    context = {
        "proforma": proforma,
        "day_left": day_left,
        "leading_number": leading_number,
        "proforma_elements": proforma_elements,
        "logo_base64": logo_base64
    }
    html_content = render_to_string("payments/print_proforma.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=proforma_content)])
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=proforma-{proforma.serial}-{proforma.number}.pdf'
    return response

@login_required(login_url="/login/")
def convert_proforma(request, proforma_id):
    proforma = get_object_or_404(Proforma, id=proforma_id)
    proforma_elements = ProformaElement.objects.exclude(element__status__id='6').filter(proforma=proforma).order_by("id")
    serials = get_object_or_404(Serial, id=1)
    def set_value(invoice): # calculate and save the value of the invoice
        invoice_elements = InvoiceElement.objects.filter(invoice=invoice).order_by("id")
        invoice.value = 0
        for e in invoice_elements:
            invoice.value += (e.element.price * e.element.quantity)
        invoice.save()

    invoice = Invoice(
        description = proforma.description,
        serial = serials.invoice_serial,
        number = serials.invoice_number,
        person = proforma.person,
        deadline = proforma.deadline,
        is_client = True,
        modified_by = request.user,
        created_by = request.user,
        currency = proforma.currency,
        proforma = proforma,
    )
    invoice.save()
    serials.invoice_number += 1
    serials.save()
    for e in proforma_elements:
        element = InvoiceElement(
            invoice = invoice,
            element = e.element,
        )
        element.save()
    set_value(invoice)
    proforma.invoice = invoice
    proforma.save()

    return redirect(
        "invoices",
    )