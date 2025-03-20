from django.urls import path
from . import views

urlpatterns = [
    path("clients/orders/", views.c_orders, name="c_orders"),
    path(
        "clients/order/<int:order_id>/<int:client_id>/", views.c_order, name="c_order"
    ),
    path("clients/offers/", views.c_offers, name="c_offers"),
    path(
        "clients/offer/<int:offer_id>/<int:client_id>/", views.c_offer, name="c_offer"
    ),
    path("providers/orders/", views.p_orders, name="p_orders"),
    path("orders/<str:token>/", views.provider_orders, name="provider_orders"),
    path(
        "providers/order/<int:order_id>/<int:provider_id>/",
        views.p_order,
        name="p_order",
    ),
    path("clients/print_order/<int:order_id>/", views.print_order, name="print_order"),
    path("clients/print_offer/<int:offer_id>/", views.print_offer, name="print_offer"),
    path("clients/convert_offer/<int:offer_id>/", views.convert_offer, name="convert_offer"),
]
