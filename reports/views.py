from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from payments.models import Payment
from invoices.models import Invoice
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models.functions import (
    TruncDay,
    TruncWeek,
    TruncMonth,
    TruncYear,
)
import json

@login_required(login_url="/login/")
def revenue(request):
    if request.method == 'POST':
        # Extragem datele de start și de sfârșit din POST request
        date_start = datetime.strptime(request.POST.get('date_start'), "%Y-%m-%d")
        date_end = datetime.strptime(request.POST.get('date_end'), "%Y-%m-%d")
    else:
        date_start = datetime.combine(timezone.localdate() - timedelta(days= 14), datetime.min.time())
        date_end = datetime.combine(timezone.localdate(), datetime.min.time())
    date_start = timezone.make_aware(date_start)
    date_end = timezone.make_aware(date_end)

    # Determinarea intervalului pentru raport
    difference = date_end - date_start
    if difference.days < 31:
        range_type = 'Täglich'
    elif difference.days < 120:
        range_type = 'Wöchentlich'
    elif difference.days < 365:
        range_type = 'Monatlich'
    else:
        range_type = 'Jährlich'
    
    # Determine truncation and step depending on range_type
    if range_type == 'Täglich':
        trunc_func = TruncDay
        step = timedelta(days=1)
        fmt = "%d"
    elif range_type == 'Wöchentlich':
        trunc_func = TruncWeek
        step = timedelta(weeks=1)
        fmt = "%V"
    elif range_type == 'Monatlich':
        trunc_func = TruncMonth
        step = timedelta(days=31)
        fmt = "%m"
    else:
        trunc_func = TruncYear
        step = timedelta(days=365)
        fmt = "%Y"

    invoices = (
        Invoice.objects.filter(created_at__gte=date_start, created_at__lt=date_end)
        .annotate(bucket=trunc_func("created_at"))
        .values("bucket", "is_client")
        .annotate(total=Sum("value"))
    )

    payments = (
        Payment.objects.filter(payment_date__gte=date_start, payment_date__lt=date_end)
        .annotate(bucket=trunc_func("payment_date"))
        .values("bucket", "is_client")
        .annotate(total=Sum("value"))
    )

    invoice_dict = {}
    for row in invoices:
        key = row["bucket"]
        entry = invoice_dict.setdefault(key, {"in": 0, "out": 0})
        value = row["total"] or 0
        if row["is_client"]:
            if value >= 0:
                entry["in"] += value
            else:
                entry["out"] += abs(value)  # => client invoice cu minus => out
        else:
            if value >= 0:
                entry["out"] += value
            else:
                entry["in"] += abs(value)  # => provider invoice cu minus => in

    payment_dict = {}
    for row in payments:
        key = row["bucket"]
        entry = payment_dict.setdefault(key, {"in": 0, "out": 0})
        value = row["total"] or 0
        if row["is_client"]:
            if value >= 0:
                entry["in"] += value
            else:
                entry["out"] += abs(value)  # => client invoice cu minus => out
        else:
            if value >= 0:
                entry["out"] += value
            else:
                entry["in"] += abs(value)  # => provider invoice cu minus => in

    revenue = []
    labels = []
    max_value = 0
    total_invoiced_in = 0
    total_invoiced_out = 0
    total_payed_in = 0
    total_payed_out = 0

    current_date = date_start
    while current_date <= date_end:
        if range_type == "Täglich":
            bucket_date = current_date.date()
            next_date = current_date + step
        elif range_type == "Wöchentlich":
            bucket_date = (current_date - timedelta(days=current_date.weekday())).date()
            next_date = current_date + step
        elif range_type == "Monatlich":
            bucket_date = current_date.replace(day=1).date()
            next_date = (current_date.replace(day=1) + step).replace(day=1)
        else:
            bucket_date = current_date.replace(month=1, day=1).date()
            next_date = current_date.replace(month=1, day=1) + step

        display_date = current_date.strftime(fmt)

        invoiced_in = float(invoice_dict.get(bucket_date, {}).get("in", 0))
        invoiced_out = float(invoice_dict.get(bucket_date, {}).get("out", 0))
        payed_in = float(payment_dict.get(bucket_date, {}).get("in", 0))
        payed_out = float(payment_dict.get(bucket_date, {}).get("out", 0))

        revenue.append({
            "range": display_date,
            "invoiced_in": invoiced_in,
            "invoiced_out": invoiced_out,
            "payed_in": payed_in,
            "payed_out": payed_out,
        })

        labels.append(display_date)
        max_value = max(max_value, abs(payed_in), abs(payed_out))

        total_invoiced_in += invoiced_in
        total_invoiced_out += invoiced_out
        total_payed_in += payed_in
        total_payed_out += payed_out

        current_date = next_date

    for item in revenue:
        item["invoiced_in_percent"] = int(item["invoiced_in"] / max_value * 100) if max_value else 0
        item["invoiced_out_percent"] = int(item["invoiced_out"] / max_value * 100) if max_value else 0
        item["payed_in_percent"] = int(item["payed_in"] / max_value * 100) if max_value else 0
        item["payed_out_percent"] = int(item["payed_out"] / max_value * 100) if max_value else 0

    chart_data = json.dumps({
        "labels": labels,
        "datasets": [
            {
                "label": "Einkommen",
                "data": [float(r["payed_in"]) for r in revenue],
                "backgroundColor": "rgba(0, 149, 255, 0.5)",
                "borderWidth": 1
            },
            {
                "label": "Auszahlungen",
                "data": [float(r["payed_out"]) for r in revenue],
                "backgroundColor": "rgba(255, 0, 0, 0.5)",
                "borderWidth": 1
            }
        ]
    })

    return render(request, "reports/revenue.html", {
        'revenue': revenue,
        'date_start': date_start.strftime("%Y-%m-%d"),
        'date_end': date_end.strftime("%Y-%m-%d"),
        'total_payed_in': '%.2f' % total_payed_in,
        'total_payed_out': '%.2f' % total_payed_out,
        'range_type': range_type,
        "chart_data": chart_data,
    })