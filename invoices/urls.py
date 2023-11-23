from django.urls import path
from . import views

urlpatterns = [
    path("payments/invoices/", views.invoices, name="invoices"),
    path("payments/invoice/<int:invoice_id>/<int:person_id>/<int:order_id>/", views.invoice, name="invoice"),
]
