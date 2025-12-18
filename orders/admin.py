from django.contrib import admin
from .models import Order, OrderElement, Offer, OfferElement

class OrderElementInline(admin.TabularInline):
    model = OrderElement
    extra = 0
    autocomplete_fields = ["service", "um", "status"]

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderElementInline]
    autocomplete_fields = ["person", "currency", "status"]
    search_fields = ["serial", "number", "description"]  # IMPORTANT
    readonly_fields = ("vat_value",)

@admin.register(OrderElement)
class OrderElementAdmin(admin.ModelAdmin):
    search_fields = ["description", "service__name", "order__serial", "order__number"]
    list_select_related = ["order", "service"]

class OfferElementInline(admin.TabularInline):
    model = OfferElement
    extra = 0
    autocomplete_fields = ["service", "um"]

@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    inlines = [OfferElementInline]
    autocomplete_fields = ["person", "currency", "status", "order"]
    search_fields = ["serial", "number", "description"]  # IMPORTANT
    readonly_fields = ("vat_value",)

@admin.register(OfferElement)
class OfferElementAdmin(admin.ModelAdmin):
    search_fields = ["description", "service__name", "offer__serial", "offer__number"]
    list_select_related = ["offer", "service"]
