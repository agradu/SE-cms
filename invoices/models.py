from django.db import models
from persons.models import Person
from orders.models import Order
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings

# Create your models here.


class Invoice(models.Model):
    serial = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=20, blank=True)
    deadline = models.DateField(default=timezone.now)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    description = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        formatted_created_at = self.created_at.strftime("%d.%m.%Y %H:%M")
        return f"{self.serial}{self.number} - {formatted_created_at} - {self.person.firstname} {self.person.lastname} {self.person.company_name} - {self.description}"
