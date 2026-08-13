from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0001_initial"),
        ("catalog", "0010_product_group_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="available_at_branches",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Branches where this product appears on POS. "
                    "Leave empty to make it available at all branches."
                ),
                related_name="available_products",
                to="branches.branch",
            ),
        ),
    ]
