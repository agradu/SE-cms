# Generated by Django 4.2.11 on 2025-03-15 10:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0004_alter_invoice_currency_alter_proforma_currency"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="payed",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
