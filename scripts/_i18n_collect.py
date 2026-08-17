"""Extract new msgids from templates and append to i18n_catalog.py."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(r"c:\Users\HP\Documents\GitHub\cafe_de_paris")
CATALOG = ROOT / "ui" / "i18n_catalog.py"
TEMPLATES = [
    "ui/templates/ui/pos.html",
    "ui/templates/ui/stock_take.html",
    "ui/templates/ui/stock_adjust.html",
    "ui/templates/ui/wastage.html",
    "ui/templates/ui/branch_transfers.html",
    "ui/templates/ui/transfers.html",
    "ui/templates/ui/stores_transfers.html",
    "ui/templates/ui/bakery_production.html",
    "ui/templates/ui/central_invoices.html",
    "ui/templates/ui/purchase_orders.html",
    "ui/templates/ui/grv.html",
    "ui/templates/ui/customer_accounts.html",
    "ui/templates/ui/includes/customer_statement_block.html",
    "ui/templates/ui/includes/supplier_statement_block.html",
    "ui/templates/ui/includes/payment_options_block.html",
] + [f"ui/templates/ui/{p.name}" for p in (ROOT / "ui/templates/ui").glob("*print*.html")]


def extract_msgids(text: str) -> set[str]:
    found: set[str] = set()
    for m in re.finditer(r"""\{%\s*trans\s+"((?:\\.|[^"\\])*)"\s*%\}""", text):
        found.add(bytes(m.group(1), "utf-8").decode("unicode_escape") if "\\" in m.group(1) else m.group(1))
    for m in re.finditer(r"""\{%\s*trans\s+'((?:\\.|[^'\\])*)'\s*%\}""", text):
        found.add(m.group(1))
    for m in re.finditer(r"""\bt\(\s*"((?:\\.|[^"\\])*)"\s*\)""", text):
        found.add(ast.literal_eval('"' + m.group(1) + '"') if "\\" in m.group(1) else m.group(1))
    for m in re.finditer(r"""\bt\(\s*'((?:\\.|[^'\\])*)'\s*\)""", text):
        found.add(m.group(1))
    return found


# Load existing keys by executing catalog carefully
ns: dict = {}
exec(CATALOG.read_text(encoding="utf-8"), ns)
existing = set(ns["TRANSLATIONS"].keys())

all_msgids: set[str] = set()
for rel in TEMPLATES:
    path = ROOT / rel
    if path.exists():
        all_msgids |= extract_msgids(path.read_text(encoding="utf-8"))

missing = sorted(m for m in all_msgids if m and m not in existing)
out = ROOT / "scripts" / "_i18n_missing_only.txt"
out.write_text("\n".join(missing), encoding="utf-8")
print(f"existing={len(existing)} found={len(all_msgids)} missing={len(missing)}")
print(f"wrote {out}")
