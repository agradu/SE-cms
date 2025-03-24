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
    
    # Calcularea veniturilor și plăților
    revenue = []
    max_value = 0
    total_client_invoiced = 0
    total_client_payed = 0
    total_provider_invoiced = 0
    total_provider_payed = 0
    current_date = date_start

    while current_date <= date_end:
        if range_type == 'Täglich':
            next_date = current_date + timedelta(days=1)
            display_date = current_date.strftime("%d")
        elif range_type == 'Wöchentlich':
            next_date = current_date + timedelta(weeks=1)
            display_date = current_date.strftime("%V")
        elif range_type == 'Monatlich':
            next_date = (current_date.replace(day=1) + timedelta(days=31)).replace(day=1)
            display_date = current_date.strftime("%m")
        else:
            next_date = current_date.replace(day=1, month=1) + timedelta(days=365)
            display_date = current_date.strftime("%Y")
        
        # Suma facturat și plătit în intervalul curent pentru clienți
        client_invoiced = Invoice.objects.filter(
            created_at__gte=current_date,
            created_at__lt=next_date,
            is_client=True
        ).aggregate(Sum('value'))['value__sum'] or 0
        print(client_invoiced)
        client_payed = Payment.objects.filter(
            payment_date__gte=current_date,
            payment_date__lt=next_date,
            is_client=True
        ).aggregate(Sum('value'))['value__sum'] or 0
        print(client_payed)
        
        # Suma facturat și plătit în intervalul curent pentru furnizori
        provider_invoiced = Invoice.objects.filter(
            created_at__gte=current_date,
            created_at__lt=next_date,
            is_client=False
        ).aggregate(Sum('value'))['value__sum'] or 0
        print(provider_invoiced)
        provider_payed = Payment.objects.filter(
            payment_date__gte=current_date,
            payment_date__lt=next_date,
            is_client=False
        ).aggregate(Sum('value'))['value__sum'] or 0
        print(provider_payed)

        # Adăugarea în listă
        revenue.append({
            'range': display_date,
            'client_invoiced': client_invoiced,
            'client_payed': client_payed,
            'provider_invoiced': provider_invoiced,
            'provider_payed': provider_payed
        })
        
        current_date = next_date
        # Actualizam valoarea maxima întâlnită
        max_value = max(max_value, client_payed, provider_payed)
    
    # Calculăm procentele și sumele totale
    for item in revenue:
        item['client_invoiced_percent'] = int(item['client_invoiced'] / max_value * 100) if max_value > 0 else 0
        item['client_payed_percent'] = int(item['client_payed'] / max_value * 100) if max_value > 0 else 0
        item['provider_invoiced_percent'] = int(item['provider_invoiced'] / max_value * 100) if max_value > 0 else 0
        item['provider_payed_percent'] = int(item['provider_payed'] / max_value * 100) if max_value > 0 else 0
        total_client_invoiced += item['client_invoiced']
        total_client_payed += item['client_payed']
        total_provider_invoiced += item['provider_invoiced']
        total_provider_payed += item['provider_payed']

    return render(request, "reports/revenue.html", {
        'revenue': revenue,
        'date_start': date_start.strftime("%Y-%m-%d"),
        'date_end': date_end.strftime("%Y-%m-%d"),
        'total_client_invoiced': total_client_invoiced,
        'total_client_payed': total_client_payed,
        'total_provider_invoiced': total_provider_invoiced,
        'total_provider_payed': total_provider_payed,
        'max_value_4': int(max_value),
        'max_value_3': int(max_value/4*3),
        'max_value_2': int(max_value/4*2),
        'max_value_1': int(max_value/4),
        'range_type': range_type
    })