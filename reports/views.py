from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Max
from payments.models import Payment
from invoices.models import Invoice
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models.functions import TruncMonth

@login_required(login_url="/login/")
def revenue(request):
    now = timezone.now()
    date_start = timezone.make_aware(datetime(now.year, now.month, 1), timezone.get_current_timezone())
    date_end = timezone.make_aware(datetime(now.year, now.month, now.day), timezone.get_current_timezone())

    if request.method == "POST":
        date_start = request.POST.get("date_start")
        date_end = request.POST.get("date_end")
        date_start = datetime.strptime(date_start, "%Y-%m-%d")
        date_end = datetime.strptime(date_end, "%Y-%m-%d")
        date_start = timezone.make_aware(date_start)
        date_end = timezone.make_aware(date_end).replace(hour=23, minute=59, second=59)

    # Create a list of all months in the range
    months = []
    current = date_start
    while current <= date_end:
        months.append(current.strftime("%Y-%m"))
        current += timedelta(days=1)
        if current.day == 1:  # Move to the first day of the next month
            current = timezone.make_aware(datetime(current.year, current.month, 1))

    # Query for payments and invoices sum grouped by month
    payments_by_month = Payment.objects.filter(payment_date__range=(date_start, date_end)).annotate(month=TruncMonth('payment_date')).values('month').annotate(total_value=Sum('value')).order_by('month')
    invoices_by_month = Invoice.objects.filter(created_at__range=(date_start, date_end)).annotate(month=TruncMonth('created_at')).values('month').annotate(total_value=Sum('value')).order_by('month')

    # Dictionary to store combined data
    combined_data = {month: {'payments_total': Decimal('0'), 'invoices_total': Decimal('0')} for month in months}

    # Update the dictionary with actual data
    for payment in payments_by_month:
        month = payment['month'].strftime("%Y-%m")
        combined_data[month]['payments_total'] = payment['total_value']

    for invoice in invoices_by_month:
        month = invoice['month'].strftime("%Y-%m")
        combined_data[month]['invoices_total'] = invoice['total_value']

    # Find max value to calculate percentages
    max_value = max([data['payments_total'] for data in combined_data.values()] + [data['invoices_total'] for data in combined_data.values()], default=Decimal('0'))

    # Prepare final list with percentages
    monthly_totals = []
    for month, data in combined_data.items():
        payments_percent = int(data['payments_total'] / max_value * 100) if max_value != 0 else 0
        invoices_percent = int(data['invoices_total'] / max_value * 100) if max_value != 0 else 0
        monthly_totals.append({
            'month': month,
            'payments_total': data['payments_total'],
            'invoices_total': data['invoices_total'],
            'payments_percent': payments_percent,
            'invoices_percent': invoices_percent
        })
    print(monthly_totals)
    return render(
        request,
        "reports/revenue.html",
        {
            'monthly_totals': monthly_totals,
            'date_start': date_start.strftime("%Y-%m-%d"),
            'date_end': date_end.strftime("%Y-%m-%d"),
        },
    )
