from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from orders.models import OrderElement
from payments.models import Payment
from services.models import Currency, Status, Service, UM
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils import timezone

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
    # CLIENT/PROVIDER INVOICES
    selected_payments = Payment.objects.filter(
        Q(person__firstname__icontains=search)
        | Q(person__lastname__icontains=search)
        | Q(person__company_name__icontains=search)
    ).filter(created_at__gte=filter_start, created_at__lte=filter_end)
    client_payments = []
    for p in selected_payments:
        client_payments.append({"payment": p, "payed": p.value})
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    if sort == "payment":
        client_payments = sorted(
            client_payments, key=lambda x: x["payment"].id, reverse=True
        )
    elif sort == "person":
        client_payments = sorted(
            client_payments, key=lambda x: x["payment"].person.firstname
        )
    elif sort == "invoice":
        client_payments = sorted(
            client_payments, key=lambda x: x["payment"].invoice.id, reverse=True
        )
    elif sort == "receipt":
        client_payments = sorted(
            client_payments, key=lambda x: x["payment"].receipt.id, reverse=True
        )
    elif sort == "assignee":
        client_payments = sorted(
            client_payments, key=lambda x: x["payment"].modified_by.first_name
        )
    elif sort == "value":
        client_payments = sorted(
            client_payments, key=lambda x: x["payment"].price, reverse=True
        )
    elif sort == "type":
        client_payments = sorted(client_payments, key=lambda x: x["payment"].type)
    elif sort == "update":
        client_payments = sorted(
            client_payments, key=lambda x: x["payment"].modified_at, reverse=True
        )
    else:
        client_payments = sorted(
            client_payments, key=lambda x: x["payment"].created_at, reverse=True
        )

    paginator = Paginator(client_payments, 10)
    payments_on_page = paginator.get_page(page)

    return render(
        request,
        "payments/payments.html",
        {
            "client_payments": payments_on_page,
            "sort": sort,
            "search": search,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )
