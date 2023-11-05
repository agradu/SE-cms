from django.urls import path
from . import views

urlpatterns = [
    path("payments/invoices/", views.invoices, name='invoices'),
]