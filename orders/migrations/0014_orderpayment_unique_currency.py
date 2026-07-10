# Generated manually for multi-currency split payments

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0013_order_payment_split"),
        ("payments", "0003_delete_paymentmethod"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="orderpayment",
            name="orders_orderpayment_unique_order_method",
        ),
        migrations.AlterField(
            model_name="orderpayment",
            name="method",
            field=models.CharField(
                choices=[("cash", "Cash"), ("bank", "Bank"), ("ecocash", "EcoCash")],
                default="cash",
                help_text="Inferred from the payment currency name when possible.",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="orderpayment",
            constraint=models.UniqueConstraint(
                fields=("order", "currency"),
                name="orders_orderpayment_unique_order_currency",
            ),
        ),
    ]
