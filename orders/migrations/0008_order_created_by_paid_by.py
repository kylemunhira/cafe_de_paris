import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0007_expense"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                help_text="POS cashier who placed the order.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="orders_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="paid_by",
            field=models.ForeignKey(
                blank=True,
                help_text="POS cashier who collected payment.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="orders_paid",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
