from decimal import Decimal

from django.db import migrations, models
from django.db.models import F


def invert_balances(apps, schema_editor):
    """Flip prepaid/debt sign convention on existing balances and ledger rows."""
    Customer = apps.get_model("customers", "Customer")
    CustomerAccountTransaction = apps.get_model("customers", "CustomerAccountTransaction")

    Customer.objects.update(account_balance=-F("account_balance"))
    CustomerAccountTransaction.objects.update(
        amount=-F("amount"),
        balance_after=-F("balance_after"),
    )


def revert_balances(apps, schema_editor):
    invert_balances(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0006_customer_account_adjustment"),
    ]

    operations = [
        migrations.RunPython(invert_balances, revert_balances),
        migrations.AlterField(
            model_name="customer",
            name="account_balance",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text=(
                    "Account balance in base currency. "
                    "Negative = prepaid credit; positive = amount owed."
                ),
                max_digits=12,
            ),
        ),
        migrations.AlterField(
            model_name="customer",
            name="credit_limit",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text=(
                    "Maximum allowed positive balance / amount owed (base currency)."
                ),
                max_digits=12,
            ),
        ),
        migrations.AlterField(
            model_name="customeraccounttransaction",
            name="amount",
            field=models.DecimalField(
                decimal_places=2,
                help_text=(
                    "Signed balance delta in base currency. "
                    "Negative for deposits/refunds, positive for charges."
                ),
                max_digits=12,
            ),
        ),
    ]
