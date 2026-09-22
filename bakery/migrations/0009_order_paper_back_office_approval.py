# Generated manually for order paper back-office approval

from django.db import migrations, models
from django.utils import timezone


def promote_existing_submitted(apps, schema_editor):
    """In-flight submitted papers were already bakery-visible; keep them usable."""
    OrderPaper = apps.get_model("bakery", "OrderPaper")
    now = timezone.now()
    OrderPaper.objects.filter(status="submitted").update(
        status="approved",
        approved_at=now,
    )


def revert_promoted_submitted(apps, schema_editor):
    OrderPaper = apps.get_model("bakery", "OrderPaper")
    OrderPaper.objects.filter(status="approved").update(
        status="submitted",
        approved_at=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("bakery", "0008_order_paper"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderpaper",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="orderpaper",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("approved", "Approved"),
                    ("accepted", "Accepted"),
                    ("fulfilled", "Fulfilled"),
                    ("cancelled", "Cancelled"),
                ],
                default="draft",
                max_length=12,
            ),
        ),
        migrations.RunPython(promote_existing_submitted, revert_promoted_submitted),
    ]
