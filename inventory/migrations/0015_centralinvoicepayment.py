import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0014_delivery_note_draft_status"),
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="centralinvoice",
            name="payment_reference",
            field=models.CharField(
                blank=True,
                help_text="Cheque, bank transfer, or other payment reference.",
                max_length=200,
            ),
        ),
        migrations.CreateModel(
            name="CentralInvoicePayment",
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
                (
                    "method",
                    models.CharField(
                        choices=[
                            ("cash", "Cash"),
                            ("bank", "Bank"),
                            ("ecocash", "EcoCash"),
                        ],
                        default="cash",
                        max_length=20,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "exchange_rate",
                    models.DecimalField(
                        blank=True, decimal_places=6, max_digits=18, null=True
                    ),
                ),
                (
                    "central_invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payments",
                        to="inventory.centralinvoice",
                    ),
                ),
                (
                    "currency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="central_invoice_payments",
                        to="payments.currency",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.AddConstraint(
            model_name="centralinvoicepayment",
            constraint=models.UniqueConstraint(
                fields=("central_invoice", "currency"),
                name="inventory_centralinvoicepayment_unique_invoice_currency",
            ),
        ),
    ]
