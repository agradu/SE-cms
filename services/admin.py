from django.contrib import admin
from .models import Status, Service, UM, Currency

# Register your models here.

admin.site.register(Service)
admin.site.register(UM)
admin.site.register(Currency)
admin.site.register(Status)
