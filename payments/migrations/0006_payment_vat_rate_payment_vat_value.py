# Generated by Django 4.2.11 on 2025-07-07 07:01

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0005_paymentelement_value"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="vat_rate",
            field=models.DecimalField(
                decimal_places=2,
                default=0.0,
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="vat_value",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
