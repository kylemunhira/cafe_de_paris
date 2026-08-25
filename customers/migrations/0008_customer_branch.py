from django.db import migrations, models
import django.db.models.deletion


def assign_existing_customers_to_churchill(apps, schema_editor):
    Branch = apps.get_model("branches", "Branch")
    Customer = apps.get_model("customers", "Customer")
    churchill = None
    for branch in Branch.objects.all():
        name = (branch.name or "").lower()
        code = (branch.code or "").upper()
        if code == "CHU" or "churchill" in name:
            churchill = branch
            break
    if churchill is None:
        return
    Customer.objects.filter(branch__isnull=True).update(branch=churchill)


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0009_highlands_dining_tables"),
        ("customers", "0007_invert_account_balance_signs"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="branch",
            field=models.ForeignKey(
                blank=True,
                help_text="Home branch for this customer account.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="customers",
                to="branches.branch",
            ),
        ),
        migrations.RunPython(
            assign_existing_customers_to_churchill,
            migrations.RunPython.noop,
        ),
    ]
