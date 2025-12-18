from django.contrib import admin
from .models import Invoice, InvoiceElement, Proforma, ProformaElement


class InvoiceElementInline(admin.TabularInline):
    model = InvoiceElement
    extra = 0
    autocomplete_fields = ["element"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceElementInline]
    autocomplete_fields = ["person", "currency"]
    search_fields = ["serial", "number", "description"]  # ✅
    readonly_fields = ("vat_rate", "vat_value",)


class ProformaElementInline(admin.TabularInline):
    model = ProformaElement
    extra = 0
    autocomplete_fields = ["element"]


@admin.register(Proforma)
class ProformaAdmin(admin.ModelAdmin):
    inlines = [ProformaElementInline]
    autocomplete_fields = ["person", "currency", "invoice"]
    search_fields = ["serial", "number", "description"]  # ✅
    readonly_fields = ("vat_rate", "vat_value",)
