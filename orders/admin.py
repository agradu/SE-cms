from django.contrib import admin
from .models import Order, OrderElement, Offer, OfferElement

# Register your models here.


class OrderElementInline(admin.TabularInline):
    model = OrderElement
    extra = 0  # Numărul de câmpuri goale pentru a adăuga noi elemente


class OrderAdmin(admin.ModelAdmin):
    model = Order
    inlines = [OrderElementInline]


# Înregistrați clasa Order cu clasa OrderAdmin
admin.site.register(Order, OrderAdmin)


class OfferElementInline(admin.TabularInline):
    model = OfferElement
    extra = 0  # Numărul de câmpuri goale pentru a adăuga noi elemente


class OfferAdmin(admin.ModelAdmin):
    model = Offer
    inlines = [OfferElementInline]


# Înregistrați clasa Order cu clasa OrderAdmin
admin.site.register(Offer, OfferAdmin)


# admin.site.register(Order)
# admin.site.register(OrderElement)
