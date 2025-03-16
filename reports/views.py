from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Max
from payments.models import Payment
from invoices.models import Invoice
from orders.models import Order
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models.functions import TruncMonth

@login_required(login_url="/login/")
def revenue(request):
    today = datetime.now().date()
    start_of_last_week = today - timedelta(days=today.weekday() + 7)
    end_of_last_week = start_of_last_week + timedelta(days=6)

    if request.method == 'POST':
        # Extragem datele de start și de sfârșit din POST request
        date_start = datetime.strptime(request.POST.get('date_start'), "%Y-%m-%d")
        date_end = datetime.strptime(request.POST.get('date_end'), "%Y-%m-%d")
    else:
        date_start = start_of_last_week
        date_end = today

    # Determinarea intervalului pentru raport
    difference = date_end - date_start
    if difference.days < 31:
        range_type = 'day'
    elif difference.days < 365:
        range_type = 'month'
    else:
        range_type = 'year'
    
    # Calcularea veniturilor
    revenue = []
    max_value = 0
    total_invoiced = 0
    total_payed = 0
    current_date = date_start

    while current_date <= date_end:
        if range_type == 'day':
            next_date = current_date + timedelta(days=1)
        elif range_type == 'month':
            next_date = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1)
        else:
            next_date = current_date.replace(day=1, month=1) + timedelta(days=365)
        
        # Suma facturat și plătit în intervalul curent
        invoiced_total = Invoice.objects.filter(
            created_at__range=[current_date, next_date]).aggregate(Sum('value'))['value__sum'] or 0
        payed_total = Payment.objects.filter(
            payment_date__range=[current_date, next_date]).aggregate(Sum('value'))['value__sum'] or 0

        # Adăugarea în listă
        revenue.append({
            'range': current_date.strftime("%Y-%m-%d"),
            'invoiced': invoiced_total,
            'payed': payed_total,
        })
        
        current_date = next_date

        # Actualizam valoarea maxima intalnita
        max_value = max(max_value, invoiced_total, payed_total)
    
    # Calculăm procentele
    for item in revenue:
        item['invoiced_percent'] = int(item['invoiced'] / max_value * 100) if max_value > 0 else 0
        item['payed_percent'] = int(item['payed'] / max_value * 100) if max_value > 0 else 0
        total_invoiced += item['invoiced']
        total_payed += item['payed']
    
    print(revenue, "total_invoiced:", total_invoiced, "total_payed:", total_payed)

    return render(request, "reports/revenue.html", {
        'revenue': revenue,
        'date_start': date_start.strftime("%Y-%m-%d"),
        'date_end': date_end.strftime("%Y-%m-%d"),
        'total_invoiced': total_invoiced,
        'total_payed': total_payed
    })