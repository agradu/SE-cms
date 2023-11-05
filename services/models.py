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
    symbol = models.CharField(max_length=3)
    name = models.CharField(max_length=20)

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
