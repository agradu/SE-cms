# Generated by Django 4.2.11 on 2024-09-20 16:35

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("persons", "0001_initial"),
        ("services", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Invoice",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "modified_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("is_recurrent", models.BooleanField(default=False)),
                ("is_client", models.BooleanField(default=True)),
                ("serial", models.CharField(blank=True, max_length=10)),
                ("number", models.CharField(blank=True, max_length=20)),
                ("deadline", models.DateField(default=django.utils.timezone.now)),
                (
                    "value",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                (
                    "description",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "cancellation_to",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cancellation_to_%(class)s",
                        to="invoices.invoice",
                    ),
                ),
                (
                    "cancelled_from",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cancelled_from_%(class)s",
                        to="invoices.invoice",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_by_%(class)s",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "currency",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="services.currency",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="modified_by_%(class)s",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="persons.person"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Proforma",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "modified_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("is_client", models.BooleanField(default=True)),
                ("serial", models.CharField(blank=True, max_length=10)),
                ("number", models.CharField(blank=True, max_length=20)),
                ("deadline", models.DateField(default=django.utils.timezone.now)),
                (
                    "value",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                (
                    "description",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_by_%(class)s",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "currency",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="services.currency",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="invoices.invoice",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="modified_by_%(class)s",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="persons.person"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ProformaElement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "element",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="orders.orderelement",
                    ),
                ),
                (
                    "proforma",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="invoices.proforma",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="InvoiceElement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "element",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="orders.orderelement",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="invoices.invoice",
                    ),
                ),
            ],
        ),
    ]
