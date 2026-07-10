from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_product_daily_stock_take"),
    ]

    operations = [
        migrations.AddField(
            model_name="productcategory",
            name="pos_station",
            field=models.CharField(
                blank=True,
                choices=[("bar", "Bar"), ("kitchen", "Kitchen")],
                default="",
                help_text="Where POS items in this category are prepared (bar or kitchen).",
                max_length=20,
            ),
        ),
    ]
