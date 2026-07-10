from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0007_seed_dining_tables"),
    ]

    operations = [
        migrations.AddField(
            model_name="branch",
            name="allow_negative_stock",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When enabled, POS sales may deduct stock below zero. "
                    "Transfers and production still require sufficient stock."
                ),
            ),
        ),
    ]
