from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from orders.models import Order, OrderElement
from persons.models import Person
from payments.models import Payment, PaymentInvoice
from .models import Invoice, InvoiceElement
from services.models import Serial
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils import timezone

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
    client_invoices = []
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
        payed = int(i_payed / i.value * 100)
        client_invoices.append(
            {"invoice": i, "payed": payed, "value": i.value, "orders": i_orders}
        )
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    if sort == "type":
        client_invoices = sorted(
            client_invoices, key=lambda x: x["invoice"].is_client, reverse=True
        )
    elif sort == "invoice":
        client_invoices = sorted(
            client_invoices, key=lambda x: x["invoice"].id, reverse=True
        )
    elif sort == "person":
        client_invoices = sorted(
            client_invoices, key=lambda x: x["invoice"].person.firstname
        )
    elif sort == "assignee":
        client_invoices = sorted(
            client_invoices, key=lambda x: x["invoice"].modified_by.first_name
        )
    elif sort == "registered":
        client_invoices = sorted(
            client_invoices, key=lambda x: x["invoice"].created_at, reverse=True
        )
    elif sort == "deadline":
        client_invoices = sorted(
            client_invoices, key=lambda x: x["invoice"].deadline, reverse=True
        )
    elif sort == "status":
        client_invoices = sorted(client_invoices, key=lambda x: x["invoice"].status.id)
    elif sort == "value":
        client_invoices = sorted(
            client_invoices, key=lambda x: x["value"], reverse=True
        )
    elif sort == "payed":
        client_invoices = sorted(client_invoices, key=lambda x: x["payed"])
    elif sort == "update":
        client_invoices = sorted(
            client_invoices, key=lambda x: x["invoice"].modified_at, reverse=True
        )
    else:
        client_invoices = sorted(
            client_invoices, key=lambda x: x["invoice"].created_at, reverse=True
        )

    paginator = Paginator(client_invoices, 10)
    invoices_on_page = paginator.get_page(page)

    return render(
        request,
        "payments/invoices.html",
        {
            "client_invoices": invoices_on_page,
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
    element = ""
    date_now = timezone.now()
    if invoice_id != 0:  # if invoice exists
        new = False
        invoice = get_object_or_404(Invoice, id=invoice_id)
        person = invoice.person
        invoice_elements = InvoiceElement.objects.filter(invoice=invoice).order_by("id")
        orders_elements = OrderElement.objects.filter(order__person=person).order_by("id")
        uninvoiced_elements = orders_elements.exclude(id__in=invoice_elements)
        if request.method == "POST":
            if "invoice_description" in request.POST:
                invoice.description = request.POST.get("invoice_description")
                if invoice.is_client == False:
                    invoice.serial = request.POST.get("invoice_serial")
                    invoice.number = request.POST.get("invoice_number")
                deadline_date = request.POST.get("deadline_date")
                deadline_naive = datetime.strptime(
                    f"{deadline_date}", "%Y-%m-%d"
                )
                invoice.deadline = timezone.make_aware(deadline_naive)
            if "invoice_element_id" in request.POST:
                invoice_element_id = int(request.POST.get("invoice_element_id"))
                try: # delete an element
                    element = InvoiceElement.objects.get(id=invoice_element_id)
                    element.delete()
                except:
                    element = ""
            if "uninvoiced_element_id" in request.POST:
                uninvoiced_element_id = int(request.POST.get("uninvoiced_element_id"))
                try: # add an element
                    element = uninvoiced_elements.get(id=uninvoiced_element_id)
                    InvoiceElement.objects.get_or_create(
                        invoice=invoice,
                        element=element
                    )
                except:
                    element = ""
            # Setting the modiffied user and date
            invoice.modified_by = request.user
            invoice.modified_at = date_now
            # Calculating the order value
            invoice.value = 0
            for e in invoice_elements:
                invoice.value += (e.element.price * e.element.quantity)
            invoice.save()

    else:  # if invoice is new
        new = True
        person = get_object_or_404(Person, id=person_id)
        order = get_object_or_404(Order, id=order_id)
        invoice = ""
        invoice_elements = InvoiceElement.objects.filter(invoice=invoice).order_by("id")
        orders_elements = OrderElement.objects.filter(order__person=person).order_by("id")
        uninvoiced_elements = orders_elements.exclude(id__in=invoice_elements)
        if request.method == "POST":
            if "invoice_description" in request.POST:
                invoice_description = request.POST.get("invoice_description")
                if order.is_client == False:
                    invoice_serial = request.POST.get("invoice_serial")
                    invoice_number = request.POST.get("invoice_number")
                else:
                    serials = Serial.objects.get(id=1)
                    invoice_serial = serials.invoice_serial
                    invoice_number = serials.invoice_number
                    serials.invoice_number += 1
                    serials.save()
                deadline_date = request.POST.get("deadline_date")
                deadline_naive = datetime.strptime(
                    f"{deadline_date}", "%Y-%m-%d"
                )
                invoice_deadline = timezone.make_aware(deadline_naive)
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
            "invoice_elements": invoice_elements,
            "uninvoiced_elements": uninvoiced_elements
        },
    )
