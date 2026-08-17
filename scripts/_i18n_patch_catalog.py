"""Patch i18n_catalog.py entries that still use English placeholders."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ui" / "i18n_catalog.py"
TR_JSON = ROOT / "scripts" / "_i18n_tr.json"


def py_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def main() -> None:
    tr = {
        k: tuple(v)
        for k, v in json.loads(TR_JSON.read_text(encoding="utf-8")).items()
    }

    ns: dict = {}
    exec(CATALOG.read_text(encoding="utf-8"), ns)
    translations: dict[str, dict[str, str]] = ns["TRANSLATIONS"]

    patched = 0
    for msgid, mapping in translations.items():
        if mapping.get("fr") != msgid:
            continue
        if msgid not in tr:
            continue
        fr, es, ar, zh = tr[msgid]
        if fr == msgid and es == msgid:
            continue
        translations[msgid] = {
            "fr": fr,
            "es": es,
            "ar": ar,
            "zh-hans": zh,
        }
        patched += 1

    header = '''"""English UI strings and translations for Café de Paris templates + JS."""

# msgid -> {lang_code: msgstr}
# Keep English as the msgid key. Languages: fr, es, ar, zh-hans
TRANSLATIONS: dict[str, dict[str, str]] = {}


def _add(msgid: str, fr: str, es: str, ar: str, zh: str) -> None:
    TRANSLATIONS[msgid] = {
        "fr": fr,
        "es": es,
        "ar": ar,
        "zh-hans": zh,
    }


'''
    lines = [header]
    for msgid, mapping in translations.items():
        lines.append(
            f"_add({py_str(msgid)}, {py_str(mapping['fr'])}, {py_str(mapping['es'])}, "
            f"{py_str(mapping['ar'])}, {py_str(mapping['zh-hans'])})\n"
        )
    lines.append("\nMSGIDS = list(TRANSLATIONS.keys())\n")
    CATALOG.write_text("".join(lines), encoding="utf-8")
    print(f"patched={patched} total={len(translations)}")


if __name__ == "__main__":
    main()
