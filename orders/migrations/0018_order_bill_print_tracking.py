from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0017_order_unpaid_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="bill_last_printed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="bill_last_printed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="orders_bill_printed",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="bill_print_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Number of guest-bill prints requested from POS.",
            ),
        ),
    ]
