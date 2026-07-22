from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0005_customer_credit_limit"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customeraccounttransaction",
            name="transaction_type",
            field=models.CharField(
                choices=[
                    ("deposit", "Deposit"),
                    ("payment", "Payment"),
                    ("refund", "Refund"),
                    ("adjustment", "Balance adjustment"),
                ],
                max_length=20,
            ),
        ),
    ]
