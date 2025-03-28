# Generated by Django 4.2.11 on 2025-02-05 14:06

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="cancellation_to",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cancellation_to_%(class)s",
                to="payments.payment",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="cancelled_from",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cancelled_from_%(class)s",
                to="payments.payment",
            ),
        ),
    ]
