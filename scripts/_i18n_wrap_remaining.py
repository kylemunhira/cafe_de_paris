"""Wrap remaining major UI strings in ops/POS templates with t() / {% trans %}."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ui" / "templates" / "ui"


def wrap_lit(text: str, s: str) -> str:
    """Wrap bare quoted occurrences of s with t(...), skipping already wrapped."""
    for q in ('"', "'"):
        lit = f"{q}{s}{q}"
        wrapped = f"t({lit})"
        if lit not in text:
            continue
        parts = text.split(lit)
        out = [parts[0]]
        for part in parts[1:]:
            if out[-1].endswith("t("):
                out.append(lit + part)
            else:
                out.append(wrapped + part)
        text = "".join(out)
    return text


def apply_pairs(text: str, pairs: list[tuple[str, str]], label: str) -> str:
    for old, new in pairs:
        if old not in text:
            if new not in text:
                print(f"  MISSING [{label}]: {old[:100]!r}")
            continue
        text = text.replace(old, new)
    return text


def patch_file(name: str, pairs: list[tuple[str, str]], literals: list[str] | None = None) -> None:
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    text = apply_pairs(text, pairs, name)
    for s in literals or []:
        text = wrap_lit(text, s)
    path.write_text(text, encoding="utf-8")
    print(f"ok {name}")


# --- pos.html ---
patch_file(
    "pos.html",
    [
        (
            '<span><strong id="split-remaining">Remaining: —</strong></span>',
            '<span><strong id="split-remaining">{% trans "Remaining:" %} —</strong></span>',
        ),
        (
            'splitRemainingEl.textContent = "Remaining: —";',
            'splitRemainingEl.textContent = `${t("Remaining:")} —`;',
        ),
        (
            "splitRemainingEl.textContent = `Remaining: ${formatCurrencyAmount(remaining, baseCurrency)}`;",
            "splitRemainingEl.textContent = `${t(\"Remaining:\")} ${formatCurrencyAmount(remaining, baseCurrency)}`;",
        ),
        (
            'title="Select for transfer"',
            'title="${t("Select for transfer")}"',
        ),
        (
            'title="Remove one unit"',
            'title="${t("Remove one unit")}"',
        ),
        (
            ">Remove 1</button>",
            ">${t(\"Remove 1\")}</button>",
        ),
        (
            'placeholder="Leave blank to skip"',
            'placeholder="${t("Leave blank to skip")}"',
        ),
    ],
    [
        "Choose any table, including ones already in use. The current table is disabled.",
        "Tap a table to select it. Highlighted tables have open dine-in orders.",
        "No tables configured. Use Manage tables to add one.",
        "No tables configured. Ask a branch manager to set up tables.",
        "In use",
        "Available",
        "Current table",
        "Back to tables",
        "Walk-in (no account)",
        "Amount due",
        "Receipt",
        "Use Remove on a line, transfer lines, or Cancel entire order below",
        "Use Remove on a line, or Cancel entire order below",
        "Use Cancel entire order below to remove this order",
        "Select lines to transfer to a table or takeaway",
        "Select for transfer",
        "Remove one unit",
        "Remove 1",
        "Transferring…",
        "Collect Table Payment",
        "No matching products",
        "Cancel",
        "Transfer to order",
        "Choose an open takeaway order, or start a new one.",
        "Close failed",
        "Closing…",
        "Fiscal day close requested",
        "Dine in",
        "TAKEAWAY",
        "DINE IN",
        "Leave blank to skip",
        "Remaining:",
    ],
)

# --- stock_take.html ---
patch_file(
    "stock_take.html",
    [
        (
            'downloadCsvBtn.textContent = isCompleted ? "Download report" : "Download CSV";',
            'downloadCsvBtn.textContent = isCompleted ? t("Download report") : t("Download CSV");',
        ),
        (
            'placeholder="Optional"',
            'placeholder="${t("Optional")}"',
        ),
    ],
    [
        "Kitchen",
        "Bar",
        "Shop",
        "Download report",
        "Download CSV",
        "No variances were posted for this filter.",
        "No ingredients in this station.",
        "Counted",
        "Optional",
    ],
)

# --- stock_adjust.html ---
patch_file(
    "stock_adjust.html",
    [],
    [
        "Ingredients",
        "Branch Ingredients",
        "Archived",
    ],
)

# --- branch_transfers.html ---
patch_file(
    "branch_transfers.html",
    [
        (
            'stockHint.textContent = "Stock leaves the sending branch when you dispatch.";',
            'stockHint.textContent = t("Stock leaves the sending branch when you dispatch.");',
        ),
        (
            'submitBtn.textContent = "Creating…";',
            'submitBtn.textContent = t("Creating…");',
        ),
    ],
    [
        "Stock leaves the sending branch when you dispatch.",
        "Creating…",
    ],
)

# --- transfers.html ---
patch_file(
    "transfers.html",
    [
        (
            'submitBtn.textContent = "Creating…";',
            'submitBtn.textContent = t("Creating…");',
        ),
    ],
    [
        "Creating…",
        "Bakery",
    ],
)

# --- stores_transfers.html ---
patch_file(
    "stores_transfers.html",
    [
        (
            """    const filterHints = {
      bakery: "Showing bakery ingredients only.",
      branch: "Showing branch ingredients only.",
      all: "Showing bakery and branch ingredients.",
    };""",
            """    const filterHints = {
      bakery: t("Showing bakery ingredients only."),
      branch: t("Showing branch ingredients only."),
      all: t("Showing bakery and branch ingredients."),
    };""",
        ),
        (
            ': "no unit cost";',
            ': t("no unit cost");',
        ),
        (
            'stockHint.textContent = `Available at stores: ${formatQty(getStoresStock(productId))}${typePart} · Unit cost: ${costLabel}`;',
            'stockHint.textContent = `${t("Available at stores:")} ${formatQty(getStoresStock(productId))}${typePart} · ${t("Unit cost:")} ${costLabel}`;',
        ),
        (
            '"mark-paid": "marked as paid",',
            '"mark-paid": t("marked as paid"),',
        ),
        (
            'approve: "Approve & deliver",',
            'approve: t("Approve & deliver"),',
        ),
    ],
    [
        "Showing bakery ingredients only.",
        "Showing branch ingredients only.",
        "Showing bakery and branch ingredients.",
        "no unit cost",
        "Available at stores:",
        "Unit cost:",
        "marked as paid",
        "Approve & deliver",
        "Ingredients",
        "Branch Ingredients",
        "Bakery",
        "Branch",
        "Central Stores",
    ],
)

# --- bakery_production.html ---
patch_file(
    "bakery_production.html",
    [],
    [
        "Uncategorized",
        "Bakery",
    ],
)

# --- central_invoices.html ---
patch_file(
    "central_invoices.html",
    [],
    [
        "Central Stores",
    ],
)

# --- purchase_orders.html ---
patch_file(
    "purchase_orders.html",
    [
        (
            'return "Central stores purchase orders use raw materials only (Ingredients category).";',
            'return t("Central stores purchase orders use raw materials only (Ingredients category).");',
        ),
        (
            'return "Bakery purchase orders use raw materials only (Ingredients category).";',
            'return t("Bakery purchase orders use raw materials only (Ingredients category).");',
        ),
        (
            'return "Kitchen supplies from the Ingredients category — milk, beans, flour, etc. These do not appear on POS.";',
            'return t("Kitchen supplies from the Ingredients category — milk, beans, flour, etc. These do not appear on POS.");',
        ),
        (
            'return "Menu items sold at the till — same products as on POS.";',
            'return t("Menu items sold at the till — same products as on POS.");',
        ),
        (
            'const placeholder = isIngredients ? "Select raw material…" : "Select POS product…";',
            'const placeholder = isIngredients ? t("Select raw material…") : t("Select POS product…");',
        ),
    ],
    [
        "Ingredients",
        "Branch Ingredients",
        "Raw material",
        "POS product",
        "Select a raw material",
        "Select a POS product",
        "Select raw material…",
        "Select POS product…",
        "Central stores purchase orders use raw materials only (Ingredients category).",
        "Bakery purchase orders use raw materials only (Ingredients category).",
        "Kitchen supplies from the Ingredients category — milk, beans, flour, etc. These do not appear on POS.",
        "Menu items sold at the till — same products as on POS.",
    ],
)

# --- grv.html ---
patch_file(
    "grv.html",
    [
        (
            'placeholder="Optional"',
            'placeholder="${t("Optional")}"',
        ),
    ],
    [
        "Optional",
        "No incoming deliveries to your branch",
        "No deliveries pending your approval",
        "No deliveries awaiting receipt",
        "No received deliveries yet",
        "No flagged GRVs",
        "No goods received vouchers found",
        "Enter valid received and damaged quantities.",
        "Received + damaged cannot exceed sent quantity.",
    ],
)

# --- customer_accounts.html ---
patch_file(
    "customer_accounts.html",
    [
        (
            '>Credit limit: —</div>',
            '>{% trans "Credit limit:" %} —</div>',
        ),
        (
            '>New balance: —</p>',
            '>{% trans "New balance:" %} —</p>',
        ),
        (
            "creditLimitEl.textContent = `Credit limit: ${formatCurrency(customer.credit_limit || 0)}`;",
            'creditLimitEl.textContent = `${t("Credit limit:")} ${formatCurrency(customer.credit_limit || 0)}`;',
        ),
        (
            'adjustPreview.textContent = "New balance: —";',
            'adjustPreview.textContent = `${t("New balance:")} —`;',
        ),
        (
            "adjustPreview.textContent = `New balance: ${formatCurrency(next)}`;",
            'adjustPreview.textContent = `${t("New balance:")} ${formatCurrency(next)}`;',
        ),
    ],
    [
        "No matching customers",
        "No customers yet",
        "No contact details",
        "Credit limit:",
        "New balance:",
    ],
)

print("remaining wrap done")
