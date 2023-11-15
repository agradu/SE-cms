from django.contrib import admin
from .models import Invoice, InvoiceElement

# Register your models here.

admin.site.register(Invoice)
admin.site.register(InvoiceElement)
