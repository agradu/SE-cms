# Generated by Django 4.2.7 on 2024-02-06 08:28

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("invoices", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="cancelled_from",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cancelled_from_%(class)s",
                to="invoices.invoice",
            ),
        ),
        migrations.AlterField(
            model_name="invoice",
            name="cancellation_to",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cancellation_to_%(class)s",
                to="invoices.invoice",
            ),
        ),
    ]
