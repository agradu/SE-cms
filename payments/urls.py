from django.urls import path
from . import views

urlpatterns = [
    path("payments/payments/", views.payments, name="payments"),
    path("payments/payment/<int:payment_id>/<int:person_id>/<int:order_id>/", views.payment, name="payment"),
]
