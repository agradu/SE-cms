from django.contrib import admin
from .models import Receipt, ReceiptInvoice

# Register your models here.

admin.site.register(Receipt)
admin.site.register(ReceiptInvoice)
