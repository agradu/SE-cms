# Generated by Django 4.2.11 on 2025-07-06 14:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0004_payment_is_recurrent"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentelement",
            name="value",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
