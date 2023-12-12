from django.urls import path
from . import views

urlpatterns = [
    path("payments/invoices/", views.invoices, name="invoices"),
    path("payments/invoice/<int:invoice_id>/<int:person_id>/<int:order_id>/", views.invoice, name="invoice"),
    path("payments/print_invoice/<int:invoice_id>/", views.print_invoice, name="print_invoice"),
    path("payments/proformas/", views.proformas, name="proformas"),
    path("payments/proforma/<int:proforma_id>/<int:person_id>/<int:order_id>/", views.proforma, name="proforma"),
    path("payments/print_proforma/<int:proforma_id>/", views.print_proforma, name="print_proforma"),
    path("payments/convert/<int:proforma_id>/", views.convert_proforma, name="convert_proforma"),
]
