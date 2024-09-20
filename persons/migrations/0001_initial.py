# Generated by Django 4.2.11 on 2024-09-20 18:36

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Person",
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
                (
                    "entity",
                    models.CharField(
                        choices=[
                            ("pi", "Private individual"),
                            ("sp", "Sole proprietor"),
                            ("co", "Company"),
                        ],
                        default="pi",
                        max_length=2,
                    ),
                ),
                (
                    "gender",
                    models.CharField(
                        choices=[("ma", "Man"), ("wo", "Woman")],
                        default="ma",
                        max_length=2,
                    ),
                ),
                ("firstname", models.CharField(max_length=100)),
                ("lastname", models.CharField(max_length=100)),
                ("identity_card", models.CharField(blank=True, max_length=30)),
                ("company_name", models.CharField(blank=True, max_length=100)),
                ("company_tax_code", models.CharField(blank=True, max_length=30)),
                ("company_iban", models.CharField(blank=True, max_length=34)),
                ("phone", models.CharField(blank=True, max_length=100)),
                ("email", models.EmailField(blank=True, max_length=255)),
                ("address", models.CharField(blank=True, max_length=255)),
                ("services", models.CharField(blank=True, max_length=255)),
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
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="modified_by_%(class)s",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
