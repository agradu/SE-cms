from django.contrib import admin
from .models import Invoice, InvoiceElement, Proforma, ProformaElement

# Register your models here.

admin.site.register(Invoice)
admin.site.register(InvoiceElement)
admin.site.register(Proforma)
admin.site.register(ProformaElement)
