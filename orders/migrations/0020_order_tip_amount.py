from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0019_bill_reprint_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="tip_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Optional tip collected at payment, in base currency.",
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name="dayendclose",
            name="tips_total",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
            ),
        ),
    ]
