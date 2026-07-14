from django.db import migrations, models

# Keep in sync with catalog.pos_catalog.POS_EXCLUDED_CATEGORIES
EXCLUDED_CATEGORY_NAMES = {
    "Ingredients",
    "Branch Ingredients",
    "Archived",
    "Components",
    "Extras",
}


def set_initial_show_on_pos(apps, schema_editor):
    ProductCategory = apps.get_model("catalog", "ProductCategory")
    for category in ProductCategory.objects.all():
        category.show_on_pos = (
            not category.is_asset
            and category.name not in EXCLUDED_CATEGORY_NAMES
        )
        category.save(update_fields=["show_on_pos"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0007_productcategory_pos_station"),
    ]

    operations = [
        migrations.AddField(
            model_name="productcategory",
            name="show_on_pos",
            field=models.BooleanField(
                default=True,
                help_text="When enabled, this category appears as a tab on POS terminals.",
            ),
        ),
        migrations.RunPython(set_initial_show_on_pos, migrations.RunPython.noop),
    ]
