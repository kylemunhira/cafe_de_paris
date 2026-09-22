from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0008_customer_branch"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text="Inactive customers are hidden from POS and account pickers.",
            ),
        ),
    ]
