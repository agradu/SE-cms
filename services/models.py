from django.db import models

# Create your models here.


class Status(models.Model):
    name = models.CharField(max_length=25)
    style = models.CharField(max_length=25, default="success")
    percent = models.SmallIntegerField(default=20)

    def __str__(self):
        return self.name


class UM(models.Model):
    name = models.CharField(max_length=15)

    def __str__(self):
        return self.name


class Currency(models.Model):
    name = models.CharField(max_length=20)
    symbol = models.CharField(max_length=3)

    def __str__(self):
        return f"{self.symbol} {self.name}"


class Service(models.Model):
    name = models.CharField(max_length=200)
    price_min = models.DecimalField(max_digits=8, decimal_places=2)
    price_max = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    um = models.ForeignKey(UM, on_delete=models.CASCADE)
    icon = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name}"

class Serial(models.Model):
    offer_serial = models.CharField(max_length=10, blank=True)
    offer_number = models.PositiveIntegerField(default=0)
    order_serial = models.CharField(max_length=10, blank=True)
    order_number = models.PositiveIntegerField(default=0)
    p_order_serial = models.CharField(max_length=10, blank=True)
    p_order_number = models.PositiveIntegerField(default=0)
    proforma_serial = models.CharField(max_length=10, blank=True)
    proforma_number = models.PositiveIntegerField(default=0)
    invoice_serial = models.CharField(max_length=10, blank=True)
    invoice_number = models.PositiveIntegerField(default=0)
    receipt_serial = models.CharField(max_length=10, blank=True)
    receipt_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Serial numbers of all entries"