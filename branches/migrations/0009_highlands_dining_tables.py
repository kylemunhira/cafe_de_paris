from django.db import migrations


HIGHLANDS_TABLE_NAMES = [f"T{index}" for index in range(1, 21)]


def _is_highlands_branch(branch):
    name = (branch.name or "").lower()
    code = (getattr(branch, "code", None) or "").upper()
    return code == "HIG" or "highland" in name


def replace_highlands_dining_tables(apps, schema_editor):
    Branch = apps.get_model("branches", "Branch")
    DiningTable = apps.get_model("branches", "DiningTable")
    for branch in Branch.objects.all():
        if not _is_highlands_branch(branch):
            continue
        DiningTable.objects.filter(branch=branch).delete()
        DiningTable.objects.bulk_create(
            [
                DiningTable(branch=branch, name=name, sort_order=index, is_active=True)
                for index, name in enumerate(HIGHLANDS_TABLE_NAMES)
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0008_branch_allow_negative_stock"),
    ]

    operations = [
        migrations.RunPython(replace_highlands_dining_tables, migrations.RunPython.noop),
    ]
