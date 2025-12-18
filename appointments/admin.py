from django.contrib import admin
from .models import Appointment

# Register your models here.

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("schedule", "status", "person", "with_person", "order")
    list_filter = ("status", "schedule")
    search_fields = (
        "description",
        "person__id",
        "with_person__id",
        "order__serial",
        "order__number",
    )
    date_hierarchy = "schedule"