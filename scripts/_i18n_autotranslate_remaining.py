"""Auto-translate remaining English-only catalog entries."""
from __future__ import annotations

import json
import time
from pathlib import Path

from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ui" / "i18n_catalog.py"

LANG_MAP = {
    "fr": "fr",
    "es": "es",
    "ar": "ar",
    "zh-hans": "zh-CN",
}


def py_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def translate(msgid: str, target: str) -> str:
    if not msgid.strip():
        return msgid
    try:
        return GoogleTranslator(source="en", target=target).translate(msgid)
    except Exception as exc:
        print(f"  warn {target!r} {msgid!r}: {exc}")
        return msgid


def main() -> None:
    ns: dict = {}
    exec(CATALOG.read_text(encoding="utf-8"), ns)
    translations: dict[str, dict[str, str]] = ns["TRANSLATIONS"]

    pending = [k for k, v in translations.items() if v["fr"] == k]
    print(f"translating {len(pending)} strings")

    for i, msgid in enumerate(pending, 1):
        translations[msgid] = {
            code: translate(msgid, target)
            for code, target in LANG_MAP.items()
        }
        print(f"[{i}/{len(pending)}] {msgid!r}")
        time.sleep(0.15)

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
    print("done")


if __name__ == "__main__":
    main()
