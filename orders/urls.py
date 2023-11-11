from django.urls import path
from . import views

urlpatterns = [
    path("clients/orders/", views.c_orders, name='c_orders'),
    path("clients/order/<int:order_id>/<int:client_id>/", views.c_order, name='c_order'),
    path("clients/offers/", views.c_offers, name='c_offers'),
    path("providers/orders/", views.p_orders, name='p_orders'),
    path("providers/order/<int:order_id>/<int:provider_id>/", views.p_order, name='p_order'),
]