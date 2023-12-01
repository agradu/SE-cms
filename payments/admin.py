from django.contrib import admin
from .models import Payment, PaymentElement

# Register your models here.

admin.site.register(Payment)
admin.site.register(PaymentElement)