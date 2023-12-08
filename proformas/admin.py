from django.contrib import admin
from .models import Proforma, ProformaElement

# Register your models here.

admin.site.register(Proforma)
admin.site.register(ProformaElement)