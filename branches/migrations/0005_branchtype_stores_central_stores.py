from django.db import migrations, models


def create_central_stores_branch(apps, schema_editor):
    Branch = apps.get_model("branches", "Branch")
    Branch.objects.get_or_create(
        name="Central Stores",
        defaults={
            "location": "Harare",
            "branch_type": "stores",
            "code": "STR",
            "is_active": True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0004_branch_code"),
    ]

    operations = [
        migrations.AlterField(
            model_name="branch",
            name="branch_type",
            field=models.CharField(
                choices=[
                    ("hq", "Headquarters"),
                    ("branch", "Branch"),
                    ("bakery", "Bakery"),
                    ("stores", "Central Stores"),
                ],
                default="branch",
                max_length=20,
            ),
        ),
        migrations.RunPython(create_central_stores_branch, migrations.RunPython.noop),
    ]
