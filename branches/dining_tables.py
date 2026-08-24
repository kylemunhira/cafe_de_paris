from .models import Branch, DiningTable

CHURCHILL_DINING_TABLE_NAMES = [
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

HIGHLANDS_DINING_TABLE_NAMES = [f"T{index}" for index in range(1, 21)]

# Backward-compatible alias used by older call sites / tests.
DEFAULT_DINING_TABLE_NAMES = CHURCHILL_DINING_TABLE_NAMES


def is_highlands_branch(branch):
    name = (getattr(branch, "name", "") or "").lower()
    code = (getattr(branch, "code", "") or "").upper()
    return code == "HIG" or "highland" in name


def is_churchill_branch(branch):
    name = (getattr(branch, "name", "") or "").lower()
    code = (getattr(branch, "code", "") or "").upper()
    return code == "CHU" or "churchill" in name


def dining_table_names_for_branch(branch):
    if is_highlands_branch(branch):
        return HIGHLANDS_DINING_TABLE_NAMES
    if is_churchill_branch(branch):
        return CHURCHILL_DINING_TABLE_NAMES
    return HIGHLANDS_DINING_TABLE_NAMES


def ensure_default_dining_tables(branch):
    if DiningTable.objects.filter(branch=branch).exists():
        return
    names = dining_table_names_for_branch(branch)
    DiningTable.objects.bulk_create(
        [
            DiningTable(branch=branch, name=name, sort_order=index, is_active=True)
            for index, name in enumerate(names)
        ]
    )


def replace_dining_tables(branch, names):
    DiningTable.objects.filter(branch=branch).delete()
    DiningTable.objects.bulk_create(
        [
            DiningTable(branch=branch, name=name, sort_order=index, is_active=True)
            for index, name in enumerate(names)
        ]
    )


def seed_dining_tables_for_all_branches():
    for branch in Branch.objects.all():
        ensure_default_dining_tables(branch)
