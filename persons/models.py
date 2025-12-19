from django.db import models
from django.conf import settings
from django.utils import timezone
from common.models import TimestampedModel


class Person(TimestampedModel):
    person_choices = [
        ("pi", "Private individual"),
        ("sp", "Sole proprietor"),
        ("co", "Company"),
    ]
    entity = models.CharField(
        max_length=2,
        choices=person_choices,
        default="pi",
    )
    gender_choices = [
        ("ma", "Man"),
        ("wo", "Woman"),
    ]
    gender = models.CharField(
        max_length=2,
        choices=gender_choices,
        default="ma",
    )
    firstname = models.CharField(max_length=100)
    lastname = models.CharField(max_length=100)
    identity_card = models.CharField(max_length=30, blank=True)
    company_name = models.CharField(max_length=100, blank=True)
    company_tax_code = models.CharField(max_length=30, blank=True)
    company_iban = models.CharField(max_length=34, blank=True)
    phone = models.CharField(max_length=100, blank=True)
    email = models.EmailField(max_length=255, blank=True)
    address = models.CharField(max_length=255, blank=True)
    services = models.CharField(max_length=255, blank=True)
    token = models.CharField(max_length=20, blank=True)

    def __str__(self):
        if self.company_name == "":
            company = ""
        else:
            company = f" / {self.company_name}"
        return f"{self.firstname} {self.lastname}{company} - {self.entity}"
