from django.db import migrations


def seed_dining_tables(apps, schema_editor):
    Branch = apps.get_model("branches", "Branch")
    DiningTable = apps.get_model("branches", "DiningTable")
    names = [
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
        "T6",
        "T7",
        "T8",
        "T9",
        "T10",
        "T11",
        "G1",
        "G2",
        "G3",
        "G4",
        "G5",
        "G6",
        "G7",
        "G-DECK",
        "G-DECK2",
    ]
    for branch in Branch.objects.all():
        if DiningTable.objects.filter(branch=branch).exists():
            continue
        DiningTable.objects.bulk_create(
            [
                DiningTable(branch=branch, name=name, sort_order=index, is_active=True)
                for index, name in enumerate(names)
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0006_dining_table"),
    ]

    operations = [
        migrations.RunPython(seed_dining_tables, migrations.RunPython.noop),
    ]
