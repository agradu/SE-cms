from django.core.management.base import BaseCommand
from orders.models import Order, OrderElement
from invoices.models import Invoice, InvoiceElement
from payments.models import Payment, PaymentElement
from django.db.models import Sum, F

class Command(BaseCommand):
    help = 'Updates all invoiced and payed values across the database'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting to update all financial records...'))

        # Actualizare invoiced pentru Orders
        for order in Order.objects.all():
            order_invoiced_total = InvoiceElement.objects.filter(
                element__order=order,
                invoice__cancelled_from__isnull=True, # Exclude cancelled invoices
                invoice__cancellation_to__isnull=True # Exclude cancelled invoices
            ).aggregate(
                total_invoiced=Sum(F('element__price') * F('element__quantity'))
            )['total_invoiced'] or 0

            order.invoiced = order_invoiced_total
            order.save()

        self.stdout.write(self.style.SUCCESS('All orders have been updated successfully.'))

        # Actualizare payed pentru Invoices
        for invoice in Invoice.objects.all():
            invoice_payed_total = PaymentElement.objects.filter(
                invoice=invoice
            ).aggregate(
                total_payed=Sum('payment__value')
            )['total_payed'] or 0

            invoice.payed = invoice_payed_total
            invoice.save()

        self.stdout.write(self.style.SUCCESS('All invoices have been updated successfully.'))

        self.stdout.write(self.style.SUCCESS('Update complete!'))
