from django.urls import path
from . import views

urlpatterns = [
    path("reports/revenue/", views.revenue, name="revenue"),
]
