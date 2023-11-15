# Generated by Django 4.2.6 on 2023-11-15 06:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("invoices", "0002_invoiceelement"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceelement",
            name="invoice",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                to="invoices.invoice",
            ),
            preserve_default=False,
        ),
    ]
