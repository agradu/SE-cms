from django.urls import path
from . import views

urlpatterns = [
    path("payments/payments/", views.payments, name="payments"),
    path("payments/payment/<int:payment_id>/<int:person_id>/<int:invoice_id>/", views.payment, name="payment"),
    path("payments/print_receipt/<int:payment_id>/", views.print_receipt, name="print_receipt"),
    path("payments/print_cancellation_receipt/<int:payment_id>/", views.print_cancellation_receipt, name="print_cancellation_receipt"),
]
