"""Generate and compile Django locale files without GNU gettext."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

from ui.i18n_catalog import TRANSLATIONS

LANGS = {
    "fr": "fr",
    "es": "es",
    "ar": "ar",
    "zh-hans": "zh_Hans",
}


def escape_po(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main() -> None:
    base = ROOT / "locale"
    for code, folder in LANGS.items():
        out_dir = base / folder / "LC_MESSAGES"
        out_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Café de Paris translations",
            'msgid ""',
            'msgstr ""',
            '"Project-Id-Version: cafe_de_paris\\n"',
            '"Report-Msgid-Bugs-To: \\n"',
            f'"Language-Team: {folder}\\n"',
            f'"Language: {code}\\n"',
            '"MIME-Version: 1.0\\n"',
            '"Content-Type: text/plain; charset=UTF-8\\n"',
            '"Content-Transfer-Encoding: 8bit\\n"',
            '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"',
            "",
        ]
        for msgid, mapping in TRANSLATIONS.items():
            lines.append(f'msgid "{escape_po(msgid)}"')
            lines.append(f'msgstr "{escape_po(mapping[code])}"')
            lines.append("")
        po_path = out_dir / "django.po"
        po_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {po_path} ({len(TRANSLATIONS)} strings)")

        mo_path = out_dir / "django.mo"
        with po_path.open("rb") as handle:
            catalog = read_po(handle)
        with mo_path.open("wb") as handle:
            write_mo(handle, catalog)
        print(f"compiled {mo_path}")


if __name__ == "__main__":
    main()
