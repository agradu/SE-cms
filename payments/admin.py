from django.contrib import admin
from .models import Payment, PaymentElement

# Register your models here.

class PaymentElementInline(admin.TabularInline):
    model = PaymentElement
    extra = 0  # Numărul de câmpuri goale pentru a adăuga noi elemente

class PaymentAdmin(admin.ModelAdmin):
    model = Payment
    inlines = [PaymentElementInline]

admin.site.register(Payment, PaymentAdmin)