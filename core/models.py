from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

from common.models import TimestampedModel
from persons.models import Person


TWOPLACES = Decimal("0.01")


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

    def format(self, amount: Decimal) -> str:
        if amount is None:
            amount = Decimal("0")
        return f"{self.symbol} {amount.quantize(TWOPLACES)}"


class Service(models.Model):
    name = models.CharField(max_length=200)
    price_min = models.DecimalField(max_digits=8, decimal_places=2)
    price_max = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    um = models.ForeignKey(UM, on_delete=models.CASCADE)
    icon = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    @property
    def price_range(self) -> tuple[Decimal, Decimal]:
        return (self.price_min, self.price_max)

    def clean(self):
        super().clean()
        if self.price_min is not None and self.price_max is not None:
            if self.price_min > self.price_max:
                raise ValidationError({"price_max": "price_max trebuie să fie >= price_min."})


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
        return "Serial numbers of all entries"

    @classmethod
    def get_solo(cls) -> "Serial":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def next_invoice(self, save: bool = True) -> int:
        self.invoice_number += 1
        if save:
            self.save(update_fields=["invoice_number"])
        return self.invoice_number

    def next_offer(self, save: bool = True) -> int:
        self.offer_number += 1
        if save:
            self.save(update_fields=["offer_number"])
        return self.offer_number


class DocumentBase(TimestampedModel):
    """
    Baza comună pentru documente (Offer/Order/Invoice/Proforma/Payment).
    IMPORTANT:
      - by default value must be >= 0
      - subclasses can override allows_negative_value() to permit storno/negative docs
    """
    person = models.ForeignKey(Person, on_delete=models.CASCADE)
    is_client = models.BooleanField(default=True)
    serial = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=20, blank=True)

    # value = NET în proiectul tău
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    vat_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    currency = models.ForeignKey(Currency, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        abstract = True

    # ---- hooks (override in subclasses if needed) ----
    def allows_negative_value(self) -> bool:
        """
        Override în subclasses care au voie să fie negative (ex: Invoice storno).
        """
        return False

    # ---- computed amounts ----
    @property
    def net(self) -> Decimal:
        return (self.value or Decimal("0")).quantize(TWOPLACES)

    @property
    def vat(self) -> Decimal:
        return (self.vat_value or Decimal("0")).quantize(TWOPLACES)

    @property
    def gross(self) -> Decimal:
        return (self.net + self.vat).quantize(TWOPLACES)

    # ---- VAT ----
    def calculate_vat_value(self) -> Decimal:
        base = self.value or Decimal("0")
        rate = self.vat_rate or Decimal("0")
        # dacă base e negativ (storno), vat va fi negativ -> corect fiscal
        return (base * rate / Decimal("100")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def recalculate_vat(self):
        self.vat_value = self.calculate_vat_value()

    # ---- Validation ----
    def clean(self):
        super().clean()

        if self.value is None:
            raise ValidationError({"value": "value nu poate fi null."})

        if self.value < 0 and not self.allows_negative_value():
            raise ValidationError({"value": "value nu poate fi negativ."})

        # (opțional) consistență: dacă vat_rate=0, vat_value ar trebui 0 (dar îl recalculăm în save)
        # Nu blocăm aici.

    def save(self, *args, **kwargs):
        self.recalculate_vat()

        update_fields = kwargs.get("update_fields")
        if update_fields:
            kwargs["update_fields"] = set(update_fields) | {"vat_value"}

        return super().save(*args, **kwargs)


class DocumentElement(models.Model):
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    quantity = models.SmallIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)
    um = models.ForeignKey(UM, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def line_total(self) -> Decimal:
        q = Decimal(str(self.quantity or 0))
        p = self.price or Decimal("0")
        return (q * p).quantize(TWOPLACES)

    def clean(self):
        super().clean()

        if self.service:
            self.um = self.service.um

        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "price nu poate fi negativ."})
