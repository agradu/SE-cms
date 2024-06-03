from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Value, CharField
from django.db.models.functions import Concat, ExtractYear, ExtractMonth
from payments.models import Payment
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, time

# Create your views here.


@login_required(login_url="/login/")
def revenue(request):
    # search elements
    now = timezone.now()
    date_start = timezone.make_aware(datetime.combine(datetime(now.year, 1, 1), time(0, 0, 0)), timezone.get_current_timezone())
    date_end = timezone.make_aware(datetime.combine(datetime(now.year, 12, 31), time(23, 59, 59)), timezone.get_current_timezone())
    if request.method == "POST":
        date_start = request.POST.get("date_start")
        date_start = datetime.strptime(date_start, "%Y-%m-%d")
        date_start = timezone.make_aware(date_start)
        date_end = request.POST.get("date_end")
        date_end = datetime.strptime(date_end, "%Y-%m-%d")
        date_end = timezone.make_aware(date_end).replace(
            hour=23, minute=59, second=59, microsecond=0
        )

    # PAYMENTS
    payments = Payment.objects.filter(payment_date__range=(date_start, date_end))
    payments = payments.annotate(
        year=ExtractYear('payment_date'),
        month=ExtractMonth('payment_date'),
        year_month=Concat(
            F('year'), Value('-'), F('month'),
            output_field=CharField()
        )
    ).values('year_month').annotate(
        total_value=Sum('value')
    ).order_by('year_month')

    return render(
        request,
        "reports/revenue.html",
        {'payments': list(payments)},
    )
