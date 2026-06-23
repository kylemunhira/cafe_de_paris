from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("zimra_fiscal", "0002_fiscalreceipt_device_branch_name_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="branchfiscalstate",
            name="invoice_sequence_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
