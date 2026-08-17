"""Find likely unwrapped English UI string literals in JS of target templates."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ui" / "templates" / "ui"
FILES = [
    "pos.html",
    "stock_take.html",
    "stock_adjust.html",
    "wastage.html",
    "branch_transfers.html",
    "transfers.html",
    "stores_transfers.html",
    "bakery_production.html",
    "central_invoices.html",
    "purchase_orders.html",
    "grv.html",
    "customer_accounts.html",
]

PAT = re.compile(r"""(?<!t\()(['"])([A-Za-z][^'"]{2,120})\1""")
SKIP_EXACT = {
    "true",
    "false",
    "null",
    "undefined",
    "module",
    "Content-Type",
    "application/json",
    "text/csv",
}


def main() -> None:
    for name in FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        m = re.search(r"(?is)<script\b[^>]*>(.*?)</script>", text)
        if not m:
            continue
        js = m.group(1)
        uniq: list[str] = []
        for mm in PAT.finditer(js):
            s = mm.group(2)
            if s in SKIP_EXACT:
                continue
            if any(x in s for x in ("${", "<", ">", "/", ".js", "api", "ui/")):
                continue
            if re.fullmatch(r"[a-z0-9_\-]+", s):
                continue
            # prefer labels / sentences
            if " " not in s and not s[0].isupper():
                continue
            if s not in uniq:
                uniq.append(s)
        if uniq:
            print(f"\n=== {name} ({len(uniq)}) ===")
            for s in uniq[:60]:
                print(f"  {s!r}")


if __name__ == "__main__":
    main()
