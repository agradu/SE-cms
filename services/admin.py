from django.contrib import admin
from .models import Status, Service, UM, Currency, Serial

# Register your models here.

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    search_fields = ["name"]

@admin.register(UM)
class UMAdmin(admin.ModelAdmin):
    search_fields = ["name"]

@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    search_fields = ["name"]

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    search_fields = ["name", "symbol"]

@admin.register(Serial)
class CurrencyAdmin(admin.ModelAdmin):
    search_fields = [
        "offer_serial", "order_serial", "p_order_serial",
        "proforma_serial", "invoice_serial", "receipt_serial"
    ]