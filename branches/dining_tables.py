from .models import Branch, DiningTable

DEFAULT_DINING_TABLE_NAMES = [
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


def ensure_default_dining_tables(branch):
    if DiningTable.objects.filter(branch=branch).exists():
        return
    DiningTable.objects.bulk_create(
        [
            DiningTable(branch=branch, name=name, sort_order=index, is_active=True)
            for index, name in enumerate(DEFAULT_DINING_TABLE_NAMES)
        ]
    )


def seed_dining_tables_for_all_branches():
    for branch in Branch.objects.all():
        ensure_default_dining_tables(branch)
