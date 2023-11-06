from django.urls import path
from . import views

urlpatterns = [
    path("clients/orders/", views.c_orders, name='c_orders'),
    path("clients/offers/", views.c_offers, name='c_offers'),
    path("providers/orders/", views.p_orders, name='p_orders'),
]