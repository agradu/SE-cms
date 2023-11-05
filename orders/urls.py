from django.urls import path
from . import views

urlpatterns = [
    path("clients/clients/", views.c_clients, name='c_clients'),
    path("clients/orders/", views.c_orders, name='c_orders'),
    path("clients/offers/", views.c_offers, name='c_offers'),
    path("providers/providers/", views.p_providers, name='p_providers'),
    path("providers/orders/", views.p_orders, name='p_orders'),
]