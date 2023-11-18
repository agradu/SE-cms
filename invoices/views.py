from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from orders.models import OrderElement
from payments.models import Payment
from .models import Invoice, InvoiceElement
from services.models import Currency, Status, Service, UM
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
        i_value = 0
        i_orders = []
        for e in invoice_elements:
            i_value += e.element.price * e.element.units
            if e.element.order not in i_orders:
                i_orders.append(e.element.order)
        i_payed = 0
        i_payments = Payment.objects.filter(invoice=i)
        for p in i_payments:
            i_payed += p.price
        payed = int(i_payed / i_value * 100)
        client_invoices.append(
            {"invoice": i, "payed": payed, "value": i_value, "orders": i_orders}
        )
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    if sort == "invoice":
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
def invoice(request, invoice_id):
    return render(
        request,
        "payments/invoice.html",
    )
