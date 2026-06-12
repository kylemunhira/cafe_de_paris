from django.db import migrations, models
from django.db.models import F


def backfill_paid_at(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.filter(status="paid", paid_at__isnull=True).update(paid_at=F("created_at"))


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_order_receipt_number_branchreceiptsequence"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="paid_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When payment was collected (used for day-end reports).",
                null=True,
            ),
        ),
        migrations.RunPython(backfill_paid_at, migrations.RunPython.noop),
    ]
