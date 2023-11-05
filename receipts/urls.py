from django.urls import path
from . import views

urlpatterns = [
    path("payments/receipts/", views.receipts, name='recipts'),
]