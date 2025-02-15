from django.contrib import admin
from .models import Invoice, InvoiceElement, Proforma, ProformaElement

# Register your models here.

class InvoiceElementInline(admin.TabularInline):
    model = InvoiceElement
    extra = 0  # Numărul de câmpuri goale pentru a adăuga noi elemente

class InvoiceAdmin(admin.ModelAdmin):
    model = Invoice
    inlines = [InvoiceElementInline]

admin.site.register(Invoice, InvoiceAdmin)


class ProformaElementInline(admin.TabularInline):
    model = ProformaElement
    extra = 0  # Numărul de câmpuri goale pentru a adăuga noi elemente

class ProformaAdmin(admin.ModelAdmin):
    model = Proforma
    inlines = [ProformaElementInline]

admin.site.register(Proforma, ProformaAdmin)