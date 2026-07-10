from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_grant_cashiers_pos_access"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffprofile",
            name="kitchen_station",
            field=models.CharField(
                blank=True,
                choices=[("bar", "Bar"), ("kitchen", "Kitchen")],
                default="",
                help_text="Kitchen display filter — only orders for this prep station (bar or kitchen).",
                max_length=20,
            ),
        ),
    ]
