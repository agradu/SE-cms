from django.urls import path
from . import views

urlpatterns = [
    path("settings/services/", views.services, name="services"),
    path(
        "settings/services/<int:service_id>/",
        views.service_detail,
        name="service_detail",
    ),
    path("settings/statuses/", views.statuses, name="statuses"),
    path(
        "settings/statuses/<int:status_id>/", views.status_detail, name="status_detail"
    ),
    path("settings/currencies/", views.currencies, name="currencies"),
    path(
        "settings/currencies/<int:currency_id>/",
        views.currency_detail,
        name="currency_detail",
    ),
    path("settings/units/", views.units, name="units"),
    path("settings/units/<int:unit_id>/", views.unit_detail, name="unit_detail"),
]
