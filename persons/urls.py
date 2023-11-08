from django.urls import path
from . import views

urlpatterns = [
    path("clients/clients/", views.c_clients, name='c_clients'),
    path("providers/providers/", views.p_providers, name='p_providers'),
    path("persons/<int:person_id>/", views.person_detail, name='person_detail'),
]