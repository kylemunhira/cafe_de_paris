from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("update", "Update"),
                    ("delete", "Delete"),
                    ("deactivate", "Deactivate"),
                    ("cancel", "Cancel"),
                    ("void", "Void"),
                ],
                max_length=20,
            ),
        ),
    ]
