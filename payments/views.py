from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from orders.models import OrderElement
from payments.models import Payment, PaymentElement
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
