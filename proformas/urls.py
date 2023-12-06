from django.urls import path
from . import views

urlpatterns = [
    path("payments/proformas/", views.proformas, name="proformas"),
    path("payments/proforma/<int:proforma_id>/<int:person_id>/<int:order_id>/", views.proforma, name="proforma"),
    path("payments/print_proforma/<int:proforma_id>/", views.print_proforma, name="print_proforma"),
]
