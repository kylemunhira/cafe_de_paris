import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchasing", "0001_initial"),
        ("orders", "0010_order_payment_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="supplier",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="expenses",
                to="purchasing.supplier",
            ),
        ),
    ]
