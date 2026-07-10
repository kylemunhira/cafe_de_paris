from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_menu_addons"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="product",
                    name="daily_stock_take",
                    field=models.BooleanField(
                        default=False,
                        help_text="Include this product in daily stock counts at branches that stock it.",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE catalog_product "
                        "ADD COLUMN IF NOT EXISTS daily_stock_take boolean "
                        "NOT NULL DEFAULT false"
                    ),
                    reverse_sql=(
                        "ALTER TABLE catalog_product "
                        "DROP COLUMN IF EXISTS daily_stock_take"
                    ),
                ),
            ],
        ),
    ]
