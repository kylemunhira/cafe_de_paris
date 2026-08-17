"""Append missing msgids to i18n_catalog.py with FR/ES/AR/ZH translations."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(r"c:\Users\HP\Documents\GitHub\cafe_de_paris")
CATALOG = ROOT / "ui" / "i18n_catalog.py"
MISSING = (ROOT / "scripts" / "_i18n_missing_only.txt").read_text(encoding="utf-8").splitlines()

# Comprehensive translations. Keys must match missing list exactly.
# Generated for Café de Paris POS / inventory / print UI.

def load_tr() -> dict[str, tuple[str, str, str, str]]:
    data = json.loads((ROOT / "scripts" / "_i18n_tr.json").read_text(encoding="utf-8"))
    return {k: tuple(v) for k, v in data.items()}


def py_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def main() -> None:
    tr = load_tr()
    ns: dict = {}
    exec(CATALOG.read_text(encoding="utf-8"), ns)
    existing = set(ns["TRANSLATIONS"].keys())

    marker = "\nMSGIDS = list(TRANSLATIONS.keys())\n"
    text = CATALOG.read_text(encoding="utf-8")
    if "# --- Ops / POS / print batch ---" in text:
        print("batch already present")
        return

    lines = ["\n# --- Ops / POS / print batch ---\n"]
    added = 0
    missing_tr = []
    for msgid in MISSING:
        if not msgid or msgid in existing:
            continue
        if msgid not in tr:
            missing_tr.append(msgid)
            fr = es = ar = zh = msgid
        else:
            fr, es, ar, zh = tr[msgid]
        lines.append(f"_add({py_str(msgid)}, {py_str(fr)}, {py_str(es)}, {py_str(ar)}, {py_str(zh)})\n")
        added += 1

    if marker not in text:
        raise SystemExit("MSGIDS marker missing")
    CATALOG.write_text(text.replace(marker, "".join(lines) + marker), encoding="utf-8")
    print(f"added={added} without_tr={len(missing_tr)}")
    if missing_tr:
        (ROOT / "scripts" / "_i18n_still_en.txt").write_text("\n".join(missing_tr), encoding="utf-8")


if __name__ == "__main__":
    main()
