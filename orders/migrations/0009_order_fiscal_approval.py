from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0008_order_created_by_paid_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="fiscal_approval_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("pending", "Pending fiscal approval"),
                    ("approved", "Fiscal receipt issued"),
                    ("failed", "Fiscal submission failed"),
                ],
                default="",
                help_text="Fiscal branches: proforma pending approval until sent to ZIMRA.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="fiscal_approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="fiscal_approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="orders_fiscal_approved",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
