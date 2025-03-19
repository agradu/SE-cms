from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, F
from orders.models import Order, OrderElement
from persons.models import Person
from payments.models import Payment, PaymentElement
from .models import Invoice, InvoiceElement, Proforma, ProformaElement
from services.models import Serial
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils.dateparse import parse_date
from django.utils import timezone
from weasyprint import HTML, CSS
import base64
from common.helpers import get_date_range, get_search_params, paginate_objects

# Create your views here.


@login_required(login_url="/login/")
def invoices(request):
    # Get data and filters
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_description = get_search_params(request)

    sort = request.GET.get("sort")

    # Query filtered invoices
    selected_invoices = Invoice.objects.filter(
        created_at__range=(filter_start, filter_end),
        description__icontains=search_description
    ).filter(
        Q(person__firstname__icontains=search_client) |
        Q(person__lastname__icontains=search_client) |
        Q(person__company_name__icontains=search_client)
    )

    # Prepare invoice list with payment details
    person_invoices = []
    for i in selected_invoices:
        invoice_elements = list(InvoiceElement.objects.filter(invoice=i).order_by("id"))
        i_orders = list(set(e.element.order for e in invoice_elements))
        payed = int(i.payed / i.value * 100) if i.value else 0
        proforma = Proforma.objects.filter(invoice=i).first()

        person_invoices.append(
            {"invoice": i, "payed": payed, "value": i.value, "orders": i_orders, "proforma": proforma}
        )

    # Sorting logic
    sort_keys = {
        "type": lambda x: x["invoice"].is_client,
        "invoice": lambda x: (x["invoice"].serial, x["invoice"].number),
        "person": lambda x: x["invoice"].person.firstname,
        "assignee": lambda x: x["invoice"].modified_by.first_name,
        "registered": lambda x: x["invoice"].created_at,
        "deadline": lambda x: x["invoice"].deadline,
        "status": lambda x: x["invoice"].status.percent,
        "value": lambda x: x["value"],
        "payed": lambda x: x["payed"],
        "update": lambda x: x["invoice"].modified_at,
    }
    
    person_invoices.sort(key=sort_keys.get(sort, lambda x: x["invoice"].created_at), reverse=(sort not in ["person", "payed"]))

    # Pagination
    invoices_on_page = paginate_objects(request, person_invoices)

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
        payed = 0 - cancelled_invoice.value,
        description = "Stornorechnung"
    )
    cancellation_invoice.save()

    cancelled_invoice.cancelled_from = cancellation_invoice
    cancelled_invoice.save()

    # Recalculate payed value for the cancelled invoice
    cancelled_invoice.payed = cancelled_invoice.paymentelement_set.aggregate(
        total=Sum(F('payment__value'))
    )['total'] or 0
    cancelled_invoice.save()

    # Căutăm o plată existentă asociată facturii anulate
    cancelled_payment = Payment.objects.filter(
        person=cancelled_invoice.person,
        is_client=cancelled_invoice.is_client,
        currency=cancelled_invoice.currency
    ).first()

    # Dacă nu există, creăm un nou obiect Payment
    if not cancelled_payment:
        cancelled_payment = Payment(
            person=cancelled_invoice.person,
            is_client=cancelled_invoice.is_client,
            modified_by=request.user,
            created_by=request.user,
            currency=cancelled_invoice.currency,
            value=cancelled_invoice.value,
            description="Stornierte Zahlung"
        )
        cancelled_payment.save()

        cancelled_payment_element = PaymentElement(
            payment = cancelled_payment,
            invoice = cancelled_invoice
        )
        cancelled_payment_element.save()

    # Determinăm tipul plății
    if cancelled_payment:
        p_type = cancelled_payment.type
    else:
        p_type = "bank"

    if p_type == "cash":
        p_serial = serials.receipt_serial
        p_number = serials.receipt_number
    else:
        p_serial = ""
        p_number = ""

    cancellation_payment = Payment(
        serial = p_serial,
        number = p_number,
        person = cancellation_invoice.person,
        is_client = cancellation_invoice.is_client,
        modified_by = request.user,
        created_by = request.user,
        currency = cancellation_invoice.currency,
        value = - cancelled_payment.value,
        description = "Stornozahlung",
        type = p_type
    )
    cancellation_payment.save()

    cancellation_payment_element = PaymentElement(
        payment = cancellation_payment,
        invoice = cancellation_invoice
    )
    cancellation_payment_element.save()
    # Making the payments connected
    cancellation_payment.cancellation_to = cancelled_payment
    cancellation_payment.save()
    cancelled_payment.cancellation_to = cancellation_payment
    cancelled_payment.save()

    serials.invoice_number += 1
    if p_type == "cash":
        serials.receipt_number += 1
    serials.save()
    for element in invoice_elements:
        c_element = InvoiceElement(
            invoice = cancellation_invoice,
            element = element.element
        )
        c_element.save()

    orders_to_update = set()
    for element in invoice_elements:
        # Asigură-te că element.element.id este ID-ul corect al OrderElement
        order_elements = OrderElement.objects.filter(id=element.element.id)
        for order_element in order_elements:
            orders_to_update.add(order_element.order)

    for order in orders_to_update:
        # Agregăm valorile facturilor pentru a obține totalul `invoiced`
        order_invoiced_total = InvoiceElement.objects.filter(
            element__order=order
        ).aggregate(
            total_invoiced=Sum(F('invoice__value'))
        )['total_invoiced'] or 0

        order.invoiced = order_invoiced_total
        order.save()

    return redirect(
        "invoices",
    )

@login_required(login_url="/login/")
def invoice(request, invoice_id, person_id, order_id):
    # Default parts
    invoice_elements = []
    uninvoiced_elements = []
    date_now = timezone.localtime()
    date_plus_five = timezone.now().date() + timedelta(days=5)
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
        last_invoice = Invoice.objects.latest('id')
        last = True if last_invoice.id == invoice.id else False
    else:
        invoice =""
        new = True
        last = True
        if is_client == False:
            invoice_serial = ""
            invoice_number = ""
    all_orders_elements = OrderElement.objects.exclude(status__percent__lt=1).filter(order__person=person).order_by("id")
    invoiced_elements = InvoiceElement.objects.filter(invoice__person=person).order_by("id")
    uninvoiced_elements = all_orders_elements.exclude(id__in=invoiced_elements.values_list('element__id', flat=True))
    # If the current invoice is a cancellation and there is a canceled invoice
    if invoice_id > 0 and invoice.cancellation_to:
        cancelled_invoice = invoice.cancellation_to
        # Items that were on the canceled invoice
        cancelled_elements = InvoiceElement.objects.filter(invoice=cancelled_invoice)
        # Items that are already billed in the current invoice
        invoiced_element_ids = InvoiceElement.objects.filter(invoice=invoice).values_list('element__id', flat=True)
        # Items that are on the canceled invoice BUT are NOT on the current invoice
        cancelled_uninvoiced_elements = cancelled_elements.exclude(element_id__in=invoiced_element_ids)
        # We convert to Order Element so it can be added to uninvoiced elements
        cancelled_uninvoiced_order_elements = OrderElement.objects.filter(
            id__in=cancelled_uninvoiced_elements.values_list('element__id', flat=True)
        )
        # We add these elements to uninvoiced_elements
        uninvoiced_elements = uninvoiced_elements | cancelled_uninvoiced_order_elements

        
    def set_value(invoice): # calculate and save the value of the invoice
        invoice_elements = InvoiceElement.objects.filter(invoice=invoice).order_by("id")
        invoice.value = 0
        orders_to_update = set()  # A set to track which orders have been updated
        for e in invoice_elements:
            invoice.value += (e.element.price * e.element.quantity)
            orders_to_update.add(e.element.order)  # Add the order of the element to the set
        if invoice.cancellation_to: # If this is a cancellation invoice, negate the value
            invoice.value = -abs(invoice.value)
        invoice.save()
        # Update the invoiced amount for each order that has elements in this invoice
        for order in orders_to_update:
            order_invoiced_total = InvoiceElement.objects.filter(
                element__order=order,
                invoice__cancelled_from__isnull=True, # Exclude cancelled invoices
                invoice__cancellation_to__isnull=True # Exclude cancelled invoices
            ).aggregate(
                total_invoiced=Sum(F('element__price') * F('element__quantity'))
            )['total_invoiced'] or 0

            order.invoiced = order_invoiced_total
            order.save()

    if invoice_id > 0:  # if invoice exists
        invoice_serial = invoice.serial
        invoice_number = invoice.number
        invoice_elements = InvoiceElement.objects.filter(invoice=invoice).order_by('element__order__created_at')
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
                        element_value = element.element.quantity * element.element.price
                        element.delete()
                        if invoice.cancellation_to:
                            i_payment = PaymentElement.objects.get(invoice=invoice).payment
                            i_payment.value += element_value
                            i_payment.save()
                            print("i_payment =",i_payment)
                except:
                    print("Element",invoice_element_id,"is missing!")
            if "uninvoiced_element_id" in request.POST:
                uninvoiced_element_id = int(request.POST.get("uninvoiced_element_id"))
                try: # add an element
                    element = uninvoiced_elements.get(id=uninvoiced_element_id)
                    element_value = element.quantity * element.price
                    InvoiceElement.objects.get_or_create(
                        invoice=invoice,
                        element=element
                    )
                    if invoice.cancellation_to:
                        i_payment = PaymentElement.objects.get(invoice=invoice).payment
                        i_payment.value -= element_value
                        i_payment.save()
                        print("i_payment =",i_payment)
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
                last = True
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
            "new": new,
            "last": last,
            "date_plus_five": date_plus_five
        },
    )

@login_required(login_url="/login/")
def print_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    invoice_elements = InvoiceElement.objects.exclude(element__status__id='6').filter(invoice=invoice).order_by("id")
    date1 = invoice.created_at.date()
    date2 = invoice.deadline
    day_left = (date2 - date1).days
    leading_invoice = invoice.number.rjust(4,'0')
    try:
        proforma = Proforma.objects.get(invoice=invoice)
        proforma_number = proforma.number
    except:
        proforma = ""
        proforma_number = ""
    leading_proforma = proforma_number.rjust(4,'0')

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
    response['Content-Disposition'] = f'filename=Rechnung-{invoice.serial}-{invoice.number}.pdf'
    return response

@login_required(login_url="/login/")
def print_cancellation_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    invoice_elements = InvoiceElement.objects.exclude(element__status__id='6').filter(invoice=invoice).order_by("id")
    date1 = invoice.created_at.date()
    date2 = invoice.deadline
    leading_storno = invoice.number.rjust(4,'0')
    leading_invoice = invoice.cancellation_to.number.rjust(4,'0')

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
        "leading_storno": leading_storno,
        "leading_invoice": leading_invoice,
        "invoice_elements": invoice_elements,
        "logo_base64": logo_base64
    }
    html_content = render_to_string("payments/print_cancellation_invoice.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=invoice_content)])
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=Stornorechnung-{invoice.serial}-{invoice.number}.pdf'
    return response


@login_required(login_url="/login/")
def proformas(request):
    # Get data and filters
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_description = get_search_params(request)

    sort = request.GET.get("sort")

    # Query filtered proformas
    selected_proformas = Proforma.objects.filter(
        created_at__range=(filter_start, filter_end),
        description__icontains=search_description
    ).filter(
        Q(person__firstname__icontains=search_client) |
        Q(person__lastname__icontains=search_client) |
        Q(person__company_name__icontains=search_client)
    )

    # Prepare proforma list
    person_proformas = []
    for p in selected_proformas:
        proforma_elements = list(ProformaElement.objects.filter(proforma=p).order_by("id"))
        p_orders = list(set(e.element.order for e in proforma_elements))
        
        person_proformas.append({"proforma": p, "value": p.value, "orders": p_orders})

    # Sorting logic
    sort_keys = {
        "proforma": lambda x: (x["proforma"].serial, x["proforma"].number),
        "person": lambda x: x["proforma"].person.firstname,
        "assignee": lambda x: x["proforma"].modified_by.first_name,
        "registered": lambda x: x["proforma"].created_at,
        "deadline": lambda x: x["proforma"].deadline,
        "status": lambda x: x["proforma"].status.id,
        "value": lambda x: x["value"],
        "update": lambda x: x["proforma"].modified_at,
    }
    
    person_proformas.sort(key=sort_keys.get(sort, lambda x: x["proforma"].created_at), reverse=(sort not in ["person", "payed"]))

    # Pagination
    proformas_on_page = paginate_objects(request, person_proformas)

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
    date_plus_five = timezone.now().date() + timedelta(days=5)
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
    all_orders_elements = OrderElement.objects.exclude(status__percent__lt=1).exclude(status__percent__gt=100).exclude(order__is_client=False).filter(order__person=person).order_by("id")
    proformed_elements = ProformaElement.objects.exclude(element__status__percent='0').filter(proforma__person=person).order_by("id")
    invoiced_elements = InvoiceElement.objects.filter(invoice__person=person).order_by("id")
    unproformed_elements = all_orders_elements.exclude(id__in=invoiced_elements.values_list('element__id', flat=True)).exclude(id__in=proformed_elements.values_list('element__id', flat=True))
    def set_value(proforma): # calculate and save the value of the proforma
        proforma_elements = ProformaElement.objects.filter(proforma=proforma).order_by("id")
        proforma.value = 0
        for e in proforma_elements:
            proforma.value += (e.element.price * e.element.quantity)
        proforma.save()
    if proforma_id > 0:  # if proforma exists
        proforma_serial = proforma.serial
        proforma_number = proforma.number
        proforma_elements = ProformaElement.objects.exclude(element__status__percent='0').filter(proforma=proforma).order_by('element__order__created_at')
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
            "new": new,
            "date_plus_five": date_plus_five
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
    response['Content-Disposition'] = f'filename=Proforma-{proforma.serial}-{proforma.number}.pdf'
    return response

@login_required(login_url="/login/")
def convert_proforma(request, proforma_id):
    proforma = get_object_or_404(Proforma, id=proforma_id)
    proforma_elements = ProformaElement.objects.exclude(element__status__percent__lt=1).filter(proforma=proforma).order_by("id")
    serials = get_object_or_404(Serial, id=1)

    def set_value(invoice): # calculate and save the value of the invoice
        invoice_elements = InvoiceElement.objects.filter(invoice=invoice).order_by("id")
        invoice.value = 0
        orders_to_update = set()  # A set to track which orders have been updated
        for e in invoice_elements:
            invoice.value += (e.element.price * e.element.quantity)
            orders_to_update.add(e.element.order)  # Add the order of the element to the set
        if invoice.cancellation_to: # If this is a cancellation invoice, negate the value
            invoice.value = -abs(invoice.value)
        invoice.save()
        # Update the invoiced amount for each order that has elements in this invoice
        for order in orders_to_update:
            order_invoiced_total = InvoiceElement.objects.filter(
                element__order=order,
                invoice__cancelled_from__isnull=True, # Exclude cancelled invoices
                invoice__cancellation_to__isnull=True # Exclude cancelled invoices
            ).aggregate(
                total_invoiced=Sum(F('element__price') * F('element__quantity'))
            )['total_invoiced'] or 0

            order.invoiced = order_invoiced_total
            order.save()

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
        "invoice",
        invoice_id=invoice.pk,
        person_id=invoice.person.pk,
        order_id=0
    )