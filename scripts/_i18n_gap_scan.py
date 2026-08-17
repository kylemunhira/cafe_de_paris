"""Scan target templates for likely remaining English UI strings."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "ui" / "templates" / "ui"

TARGETS = [
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
    "includes/customer_statement_block.html",
    "includes/supplier_statement_block.html",
    "includes/payment_options_block.html",
] + [p.name for p in TEMPLATES.glob("*print*.html")]

CALL_RE = re.compile(
    r"""\b(showToast|confirm|alert)\(\s*(?!t\()(['"])((?:\\.|(?!\2).)*)\2"""
)
# label/button/option/th/h2-h3 text not already using {% trans
HTML_TEXT_RE = re.compile(
    r""">([A-Z][^<{%]{1,80}?)</(button|label|option|th|h[1-6]|span|p|a|strong|div)>"""
)
PLACEHOLDER_RE = re.compile(r"""placeholder="([^"{%][^"]{1,80})" """)
ARIA_RE = re.compile(r"""aria-label="([^"{%][^"]{1,80})" """)


def script_body(text: str) -> str:
    m = re.search(r"(?is)<script\b[^>]*>(.*?)</script>", text)
    return m.group(1) if m else ""


def main() -> None:
    for rel in TARGETS:
        path = TEMPLATES / rel
        if not path.exists():
            print(f"MISSING FILE {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        js = script_body(text)
        # strip django tags from HTML for leftover scan
        html = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", text)
        html_no_trans = re.sub(r"""\{%\s*trans\s+["'](?:\\.|[^"\\])*["']\s*%\}""", "§", html)

        calls = [(m.group(1), m.group(3)[:90]) for m in CALL_RE.finditer(js)]
        # filter out empty / paths
        calls = [(fn, s) for fn, s in calls if s and not s.startswith(("/", "http", "#"))]

        html_hits = []
        for m in HTML_TEXT_RE.finditer(html_no_trans):
            s = m.group(1).strip()
            if not s or s.startswith("{{") or "§" in s:
                continue
            # skip pure numbers / symbols
            if re.fullmatch(r"[\d\s\-–—./:#]+", s):
                continue
            html_hits.append((m.group(2), s[:90]))

        ph = PLACEHOLDER_RE.findall(html_no_trans)
        aria = ARIA_RE.findall(html_no_trans)

        # JS string literals assigned to textContent/innerHTML/title that look like UI
        js_ui = []
        for m in re.finditer(
            r"""(?:textContent|innerHTML|innerText|title|placeholder)\s*=\s*(?!t\()(['"])([^'"]{2,80})\1""",
            js,
        ):
            js_ui.append(m.group(2))

        if calls or html_hits or ph or aria or js_ui:
            print(f"\n=== {rel} ===")
            if calls:
                print(f"  unwrapped calls ({len(calls)}):")
                for fn, s in calls[:12]:
                    print(f"    {fn}: {s!r}")
            if html_hits:
                print(f"  html text ({len(html_hits)}):")
                for tag, s in html_hits[:15]:
                    print(f"    <{tag}> {s!r}")
            if ph:
                print(f"  placeholders: {ph[:8]}")
            if aria:
                print(f"  aria: {aria[:8]}")
            if js_ui:
                print(f"  js textContent-ish ({len(js_ui)}): {js_ui[:12]}")
        else:
            print(f"ok {rel}")


if __name__ == "__main__":
    main()
