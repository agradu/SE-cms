from payments.models import PaymentElement
from django.db.models import Q, Sum, F
from datetime import datetime, timedelta
from django.utils import timezone

# helping functions

def update_invoice_payed(invoice):
    invoice.payed = PaymentElement.objects.filter(invoice=invoice).aggregate(
        total=Sum("value")
    )["total"] or 0
    invoice.save()

def set_payment_value(payment, value=None):
    elements = PaymentElement.objects.filter(payment=payment).order_by("invoice__created_at")
    invoices = set()

    if len(elements) == 1 and value is not None:
        e = elements.first()
        total_payed = PaymentElement.objects.filter(invoice=e.invoice).exclude(payment=payment).aggregate(total=Sum("value"))["total"] or 0
        remaining = e.invoice.value - total_payed
        e.value = min(value, remaining) if value > 0 else -min(abs(value), remaining)
        e.save()
        payment.value = e.value
        invoices.add(e.invoice)
    else:
        total = 0
        for e in elements:
            if e.value == 0:
                total_payed = PaymentElement.objects.filter(invoice=e.invoice).exclude(payment=payment).aggregate(total=Sum("value"))["total"] or 0
                remaining = e.invoice.value - total_payed
                e.value = remaining
                e.save()
            total += e.value
            invoices.add(e.invoice)
        payment.value = total

    payment.save()
    for inv in invoices:
        update_invoice_payed(inv)

def parse_payment_date(posted_date, fallback_date):
    try:
        naive = datetime.strptime(posted_date, "%Y-%m-%d")
        return timezone.make_aware(naive)
    except:
        return fallback_date
    
def get_serial_and_number(is_client, payment_type, serials, assign=False):
    """
    Returnează serial și număr doar pentru plăți cash.
    Dacă assign=True, incrementează serialul în baza de date.
    """
    if is_client and payment_type == "cash":
        serial = serials.receipt_serial
        number = serials.receipt_number
        if assign:
            serials.receipt_number += 1
            serials.save()
        return serial, number
    return "", ""