import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def assign_bakery_branch(apps, schema_editor):
    Branch = apps.get_model("branches", "Branch")
    ProductionOrder = apps.get_model("bakery", "ProductionOrder")
    bakery = Branch.objects.filter(branch_type="bakery").order_by("id").first()
    if bakery is None:
        return
    ProductionOrder.objects.filter(branch__isnull=True).update(branch_id=bakery.id)


class Migration(migrations.Migration):

    dependencies = [
        ("bakery", "0002_alter_recipe_options"),
        ("branches", "0005_branchtype_stores_central_stores"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="productionorder",
            name="branch",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="production_orders",
                to="branches.branch",
            ),
        ),
        migrations.AddField(
            model_name="productionorder",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="production_orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_bakery_branch, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="productionorder",
            name="branch",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="production_orders",
                to="branches.branch",
            ),
        ),
    ]
