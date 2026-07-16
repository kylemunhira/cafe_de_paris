"""Generate Café de Paris whole-app process-flow PDF."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent / "Cafe_de_Paris_Process_Flow.pdf"

BRAND = colors.HexColor("#1a2332")
ACCENT = colors.HexColor("#b8956a")
MUTED = colors.HexColor("#5c6570")
LIGHT = colors.HexColor("#f5f2eb")
LINE = colors.HexColor("#d4cfc4")
WHITE = colors.white
GREEN = colors.HexColor("#2d6a4f")
BLUE = colors.HexColor("#1d4e89")
ORANGE = colors.HexColor("#9a5b1a")


class FlowBox(Flowable):
    """Horizontal arrow-linked process steps."""

    def __init__(self, steps, width=170 * mm, box_h=18 * mm):
        super().__init__()
        self.steps = steps
        self.box_h = box_h
        self._width = width
        n = len(steps)
        gap = 8 * mm if n <= 4 else 5 * mm
        self.box_w = (width - gap * (n - 1)) / n
        self.height = box_h + 2 * mm

    def wrap(self, availWidth, availHeight):
        self._width = min(self._width, availWidth)
        n = len(self.steps)
        gap = 8 * mm if n <= 4 else 5 * mm
        self.box_w = (self._width - gap * (n - 1)) / n
        return self._width, self.height

    def draw(self):
        c = self.canv
        n = len(self.steps)
        gap = 8 * mm if n <= 4 else 5 * mm
        x = 0
        for i, label in enumerate(self.steps):
            c.setFillColor(BRAND)
            c.roundRect(x, 2 * mm, self.box_w, self.box_h - 2 * mm, 3, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 7.5)
            # wrap label
            words = label.split()
            lines, cur = [], ""
            for w in words:
                trial = f"{cur} {w}".strip()
                if c.stringWidth(trial, "Helvetica-Bold", 7.5) < self.box_w - 4 * mm:
                    cur = trial
                else:
                    if cur:
                        lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
            lines = lines[:3]
            total_h = len(lines) * 9
            y = 2 * mm + (self.box_h - 2 * mm) / 2 + total_h / 2 - 7
            for line in lines:
                c.drawCentredString(x + self.box_w / 2, y, line)
                y -= 9
            if i < n - 1:
                ax = x + self.box_w + 1 * mm
                ay = 2 * mm + (self.box_h - 2 * mm) / 2
                c.setStrokeColor(ACCENT)
                c.setFillColor(ACCENT)
                c.setLineWidth(1.5)
                c.line(ax, ay, ax + gap - 2 * mm, ay)
                path = c.beginPath()
                tip = ax + gap - 1 * mm
                path.moveTo(tip, ay)
                path.lineTo(tip - 2.5 * mm, ay + 1.5 * mm)
                path.lineTo(tip - 2.5 * mm, ay - 1.5 * mm)
                path.close()
                c.drawPath(path, fill=1, stroke=0)
            x += self.box_w + gap


class StockDiagram(Flowable):
    """ASCII-style stock network diagram as drawn boxes."""

    def __init__(self, width=170 * mm, height=72 * mm):
        super().__init__()
        self._width = width
        self.height = height

    def wrap(self, availWidth, availHeight):
        self._width = min(self._width, availWidth)
        return self._width, self.height

    def _box(self, c, x, y, w, h, title, sub, fill):
        c.setFillColor(fill)
        c.setStrokeColor(BRAND)
        c.setLineWidth(0.8)
        c.roundRect(x, y, w, h, 4, fill=1, stroke=1)
        c.setFillColor(WHITE if fill != LIGHT else BRAND)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + w / 2, y + h / 2 + 2, title)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(WHITE if fill != LIGHT else MUTED)
        c.drawCentredString(x + w / 2, y + h / 2 - 8, sub)

    def _arrow(self, c, x1, y1, x2, y2, label=""):
        c.setStrokeColor(ACCENT)
        c.setFillColor(ACCENT)
        c.setLineWidth(1.2)
        c.line(x1, y1, x2, y2)
        # simple tip
        import math

        ang = math.atan2(y2 - y1, x2 - x1)
        tip_len = 3.5 * mm
        path = c.beginPath()
        path.moveTo(x2, y2)
        path.lineTo(
            x2 - tip_len * math.cos(ang - 0.4),
            y2 - tip_len * math.sin(ang - 0.4),
        )
        path.lineTo(
            x2 - tip_len * math.cos(ang + 0.4),
            y2 - tip_len * math.sin(ang + 0.4),
        )
        path.close()
        c.drawPath(path, fill=1, stroke=0)
        if label:
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 6)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 + 2 * mm
            c.drawCentredString(mx, my, label)

    def draw(self):
        c = self.canv
        w = self._width
        # layout
        supplier_w, box_h = 28 * mm, 16 * mm
        stores_w = 36 * mm
        mid_w = 30 * mm
        bakery_w = 30 * mm
        cafe_w = 30 * mm
        ext_w = 32 * mm

        stores_x = (w - stores_w) / 2
        stores_y = 48 * mm
        supplier_x = 8 * mm
        supplier_y = 48 * mm
        bakery_x = 18 * mm
        bakery_y = 22 * mm
        cafe_x = w / 2 - cafe_w / 2
        cafe_y = 6 * mm
        ext_x = w - ext_w - 8 * mm
        ext_y = 48 * mm

        self._box(c, supplier_x, supplier_y, supplier_w, box_h, "Supplier", "External", BLUE)
        self._box(c, stores_x, stores_y, stores_w, box_h, "Central Stores", "Purchases hub", BRAND)
        self._box(c, bakery_x, bakery_y, bakery_w, box_h, "Bakery", "Produce goods", ORANGE)
        self._box(c, cafe_x, cafe_y, cafe_w, box_h, "Café Branch", "POS + kitchen", GREEN)
        self._box(c, ext_x, ext_y, ext_w, box_h, "Ext. Customer", "Wholesale", MUTED)

        self._arrow(
            c,
            supplier_x + supplier_w,
            supplier_y + box_h / 2,
            stores_x,
            stores_y + box_h / 2,
            "Purchase",
        )
        self._arrow(
            c,
            stores_x + stores_w,
            stores_y + box_h / 2,
            ext_x,
            ext_y + box_h / 2,
            "Central Invoice",
        )
        # stores down to bakery (ingredients path note)
        self._arrow(
            c,
            stores_x + 8 * mm,
            stores_y,
            bakery_x + bakery_w / 2,
            bakery_y + box_h,
            "Ingredients",
        )
        # bakery to cafe
        self._arrow(
            c,
            bakery_x + bakery_w,
            bakery_y + box_h / 2,
            cafe_x,
            cafe_y + box_h / 2 + 4 * mm,
            "Bakery DN",
        )
        # stores to cafe
        self._arrow(
            c,
            stores_x + stores_w / 2,
            stores_y,
            cafe_x + cafe_w / 2,
            cafe_y + box_h,
            "Stores DN",
        )


def styles():
    base = getSampleStyleSheet()
    s = {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            textColor=BRAND,
            alignment=TA_CENTER,
            spaceAfter=8,
            leading=34,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=6,
            leading=16,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=BRAND,
            spaceBefore=14,
            spaceAfter=8,
            borderPadding=3,
            leading=18,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=ACCENT,
            spaceBefore=10,
            spaceAfter=5,
            leading=14,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=BRAND,
            leading=12,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
            leading=11,
            spaceAfter=3,
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=8,
            textColor=BRAND,
            leading=11,
            spaceAfter=2,
            leftIndent=6,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=BRAND,
            leading=12,
            leftIndent=4,
        ),
    }
    return s


def section_rule():
    t = Table([[""]], colWidths=[170 * mm])
    t.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 1.5, ACCENT),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def simple_table(headers, rows, col_widths=None):
    style_n = ParagraphStyle(
        "th", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, leading=10
    )
    style_c = ParagraphStyle(
        "td", fontName="Helvetica", fontSize=8, textColor=BRAND, leading=10
    )
    data = [[Paragraph(h, style_n) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), style_c) for c in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("BACKGROUND", (0, 1), (-1, -1), LIGHT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT, WHITE]),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def bullets(items, s):
    return ListFlowable(
        [ListItem(Paragraph(i, s["bullet"]), leftIndent=10, bulletColor=ACCENT) for i in items],
        bulletType="bullet",
        start="•",
        leftIndent=12,
        bulletFontSize=9,
        bulletColor=ACCENT,
    )


def add_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, A4[1] - 12 * mm, A4[0] - 18 * mm, A4[1] - 12 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, A4[1] - 10 * mm, "Café de Paris — Application Process Flow")
    canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 10 * mm, "Confidential — Operations")
    canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
    canvas.drawCentredString(A4[0] / 2, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build():
    s = styles()
    story = []

    # Cover
    story.append(Spacer(1, 45 * mm))
    story.append(Paragraph("Café de Paris", s["cover_title"]))
    story.append(Paragraph("Application Process Flow", s["cover_title"]))
    story.append(Spacer(1, 6 * mm))
    story.append(section_rule())
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "End-to-end process map for POS, kitchen, bakery, central stores, "
            "inventory, fiscalization, reporting, and client apps.",
            s["cover_sub"],
        )
    )
    story.append(Paragraph("Stack: Django + DRF · Web UI · Desktop POS · Android Kitchen/POS", s["cover_sub"]))
    story.append(Paragraph("Timezone: Africa/Harare · Tax: inclusive (default 15.5%) · Fiscal: ZIMRA", s["cover_sub"]))
    story.append(Spacer(1, 20 * mm))
    story.append(
        Paragraph(
            "Generated from the café_de_paris codebase for operations and onboarding.",
            s["small"],
        )
    )
    story.append(PageBreak())

    # 1 Overview
    story.append(Paragraph("1. System overview", s["h1"]))
    story.append(section_rule())
    story.append(
        Paragraph(
            "Café de Paris is a multi-branch restaurant and bakery operations platform. "
            "Central Stores purchases goods; the Bakery produces finished products; café Branches "
            "sell via POS; HQ oversees users, fiscal rules, and network stock.",
            s["body"],
        )
    )
    story.append(Paragraph("Stock network", s["h2"]))
    story.append(StockDiagram())
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            "Master flows: (1) Buy → Stores · (2) Produce at Bakery · (3) Deliver to Café · "
            "(4) Sell at POS · (5) Fiscalise · (6) Day-end · (7) Wholesale Central Invoice.",
            s["small"],
        )
    )

    # 2 Modules
    story.append(Paragraph("2. Modules (Django apps)", s["h1"]))
    story.append(section_rule())
    story.append(
        simple_table(
            ["Module", "Responsibility"],
            [
                ["accounts", "Staff roles, branch access, login (web / desktop / kitchen / mobile)"],
                ["branches", "Branches, dining tables, fiscal day open/close"],
                ["catalog", "Categories, products, menu add-ons, POS stations"],
                ["customers", "Customers, prepaid accounts, family/staff pricing"],
                ["inventory", "Branch stock, movements, transfers, delivery notes, central invoices, stock take"],
                ["purchasing", "Suppliers, purchases into Central Stores, statements"],
                ["orders", "POS orders, payments, kitchen status, expenses, day-end closes"],
                ["payments", "Currencies and exchange rates"],
                ["zimra_fiscal", "Proforma → ZIMRA fiscal receipt submit"],
                ["bakery", "Recipes (BOM), production orders, costing"],
                ["reports", "Sales, day-end, VAT, ingredients, customer balances"],
                ["sync", "Desktop offline pull/push (idempotent client orders)"],
                ["ui", "Web management console and print templates"],
            ],
            col_widths=[32 * mm, 138 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            "Clients: <b>desktop/</b> Electron offline POS · <b>android-kitchen/</b> kitchen display + cashier POS (Bluetooth ESC/POS).",
            s["body"],
        )
    )

    # 3 Branch types
    story.append(Paragraph("3. Branch types", s["h1"]))
    story.append(section_rule())
    story.append(
        simple_table(
            ["Type", "Code", "Role"],
            [
                ["Headquarters", "hq", "Oversight; users; network visibility; admin"],
                ["Branch (café)", "branch", "POS, kitchen, GRV receive, stock take, expenses"],
                ["Bakery", "bakery", "Production from recipes; outbound bakery delivery notes"],
                ["Central Stores", "stores", "Purchases; hold stock; stores transfers; central invoices"],
            ],
            col_widths=[38 * mm, 28 * mm, 104 * mm],
        )
    )

    # 4 Roles
    story.append(Paragraph("4. Roles & access", s["h1"]))
    story.append(section_rule())
    story.append(
        simple_table(
            ["Role", "Typical use"],
            [
                ["HQ Admin", "All branches; users; suppliers; approve POs & fiscal"],
                ["Branch Manager", "Own branch ops; dining tables; approve fiscal; no HQ dashboard"],
                ["Cashier", "POS + payment; stock take; fiscal print if enabled"],
                ["Waiter", "POS order entry only (no payment); no management console"],
                ["Baker", "Bakery production / bakery transfer path"],
                ["Staff", "GRV receive (branch / HQ / stores) when configured"],
            ],
            col_widths=[40 * mm, 130 * mm],
        )
    )
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "Landing after login: Waiter/Cashier → POS · GRV staff → GRV · Branch manager → POS or Orders · else → Dashboard.",
            s["small"],
        )
    )

    story.append(PageBreak())

    # 5 POS
    story.append(Paragraph("5. POS, kitchen & payment", s["h1"]))
    story.append(section_rule())
    story.append(Paragraph("5.1 Place order", s["h2"]))
    story.append(
        FlowBox(["Select branch / mode", "Browse catalog + add-ons", "POST /api/orders/", "Print kitchen ticket"])
    )
    story.append(Spacer(1, 2 * mm))
    story.append(
        bullets(
            [
                "Modes: <b>Order</b> (place) or <b>Receipt</b> (pay).",
                "Optional customer, dine-in table, or takeaway.",
                "Order status = open; kitchen status = pending.",
                "Clients: web POS, desktop Electron, Android POS.",
            ],
            s,
        )
    )

    story.append(Paragraph("5.2 Kitchen preparation", s["h2"]))
    story.append(FlowBox(["Pending on display", "Start preparing", "Mark ready", "Drops when paid"]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "Station filter (bar / kitchen) via staff kitchen_station vs category pos_station. "
            "Adding items to an open order resets kitchen to pending.",
            s["body"],
        )
    )

    story.append(Paragraph("5.3 Collect payment", s["h2"]))
    story.append(
        FlowBox(["Select open order", "Tender / account", "Assign receipt #", "Consume stock + print"])
    )
    story.append(Spacer(1, 2 * mm))
    story.append(
        bullets(
            [
                "Waiters cannot collect payment.",
                "Tenders: cash / bank / EcoCash / multi-currency split, or customer account.",
                "Receipt number format: {BRANCH_CODE}{DDMMYY}{daily#}.",
                "Cancel open unpaid (no stock). Void paid non-fiscalized (restock). Fiscalised approved cannot void.",
            ],
            s,
        )
    )

    # 6 Fiscal
    story.append(Paragraph("6. Fiscalization (ZIMRA)", s["h1"]))
    story.append(section_rule())
    story.append(Paragraph("Non-fiscal branch", s["h2"]))
    story.append(FlowBox(["Pay", "Receipt number", "Print thermal receipt", "Done"]))
    story.append(Paragraph("Fiscal branch", s["h2"]))
    story.append(
        FlowBox(["Open fiscal day", "Pay → proforma pending", "Manager approve", "ZIMRA + fiscal print"])
    )
    story.append(Spacer(1, 2 * mm))
    story.append(
        bullets(
            [
                "Close fiscal day via branch fiscal-day API.",
                "VAT report includes only fiscalised (approved) sales — pending proforma excluded.",
                "Screens: Invoices, Receipts, POS print templates.",
            ],
            s,
        )
    )

    # 7 Bakery
    story.append(Paragraph("7. Bakery production", s["h1"]))
    story.append(section_rule())
    story.append(
        FlowBox(["Define recipe BOM", "Preview stock check", "Complete production", "Finished goods + stock"])
    )
    story.append(Spacer(1, 2 * mm))
    story.append(
        bullets(
            [
                "Consumes ingredients (PRODUCTION_CONSUME); adds finished goods (PRODUCTION_OUTPUT) at bakery.",
                "Only central bakery branch; finished bakery-transfer products only.",
                "Finished goods leave bakery via Bakery Delivery Notes (not Central Invoice).",
            ],
            s,
        )
    )

    story.append(PageBreak())

    # 8 Purchases & transfers
    story.append(Paragraph("8. Purchases, transfers & GRV", s["h1"]))
    story.append(section_rule())

    story.append(Paragraph("8.1 Purchases into Central Stores", s["h2"]))
    story.append(FlowBox(["Choose stores + supplier", "Add product lines", "POST purchase", "Stock in (PURCHASE)"]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "Create is immediate receive (status RECEIVED). HQ/global approve path exists for legacy draft POs. "
            "Supplier statements available under Reports.",
            s["body"],
        )
    )

    story.append(Paragraph("8.2 Bakery delivery note", s["h2"]))
    story.append(FlowBox(["Create from bakery", "Deduct bakery stock", "Approve receive", "Credit destination"]))
    story.append(
        Paragraph(
            "On create: DELIVERY_OUT at bakery. On approve: DELIVERY_IN at destination and status DELIVERED "
            "(no separate dispatch step for bakery notes).",
            s["small"],
        )
    )

    story.append(Paragraph("8.3 Stores delivery note / transfer invoice", s["h2"]))
    story.append(
        FlowBox(["Create (REQUESTED)", "Approve", "Dispatch (stock out)", "GRV deliver (stock in)"])
    )
    story.append(
        Paragraph(
            "Optional mark transfer invoice paid. Print delivery note or transfer invoice. "
            "GRV screen used by branch/HQ/stores staff; global users use transfer pages.",
            s["small"],
        )
    )

    story.append(Paragraph("8.4 Central Invoice (wholesale)", s["h2"]))
    story.append(
        FlowBox(["Select customer + SKUs", "Create invoice", "Deduct stores stock", "Mark paid / cancel"])
    )
    story.append(
        Paragraph(
            "Number CI{STORES_CODE}{id}. Cancel restocks via CENTRAL_INVOICE_CANCEL. "
            "This sells to external customers — not inter-branch transfer.",
            s["small"],
        )
    )

    # 9 Inventory
    story.append(Paragraph("9. Inventory & stock take", s["h1"]))
    story.append(section_rule())
    story.append(
        Paragraph(
            "Source of truth: <b>BranchInventory</b> (qty per branch × product) + append-only <b>StockMovement</b> ledger.",
            s["body"],
        )
    )
    story.append(
        simple_table(
            ["Reason", "Triggered by"],
            [
                ["PURCHASE", "Purchase create / receive"],
                ["PRODUCTION_CONSUME / OUTPUT", "Bakery production complete"],
                ["DELIVERY_OUT / IN / CANCEL", "Delivery notes"],
                ["TRANSFER_OUT / IN", "Legacy StockTransfer"],
                ["SALE / SALE_VOID", "Order pay / void"],
                ["CENTRAL_INVOICE / CANCEL", "Central invoice"],
                ["STOCK_TAKE", "Complete stock take"],
                ["MANUAL_ADD / SET / ADJUSTMENT", "Inventory adjust API"],
            ],
            col_widths=[55 * mm, 115 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Sale stock rules", s["h2"]))
    story.append(
        bullets(
            [
                "Bakery sellable SKU on order → deduct finished product at selling branch.",
                "Kitchen product with recipe → deduct Branch Ingredients × recipe qty.",
                "No recipe → no stock deduction.",
                "POS may go negative if branch allow_negative_stock; transfers/production always require stock.",
            ],
            s,
        )
    )
    story.append(Paragraph("Stock take → day end", s["h2"]))
    story.append(FlowBox(["Create daily take", "Count / import lines", "Complete (adjust)", "Day-end check OK"]))

    story.append(PageBreak())

    # 10 Day end & reports
    story.append(Paragraph("10. Day end & reports", s["h1"]))
    story.append(section_rule())
    story.append(Paragraph("Day-end cash-up", s["h2"]))
    story.append(
        FlowBox(["Daily stock take done", "Load day-end report", "Count till per currency", "Save DayEndClose + print"])
    )
    story.append(
        Paragraph(
            "Expected till ≈ sales + deposits − expenses. Expenses logged from POS/expenses API and included in day end.",
            s["body"],
        )
    )
    story.append(Paragraph("Report suite", s["h2"]))
    story.append(
        simple_table(
            ["Report", "Purpose"],
            [
                ["Ingredient Stock", "On-hand ingredients by branch"],
                ["Ingredient Usage", "Consumption over a period"],
                ["Day End", "Cash-up, variance, activity"],
                ["Customer Balances", "Prepaid account balances"],
                ["VAT", "Fiscalised sales VAT"],
                ["Supplier Statements", "Supplier spend over period"],
                ["Summary / Profit / CSV", "Management analytics APIs"],
            ],
            col_widths=[42 * mm, 128 * mm],
        )
    )

    # 11 Customers
    story.append(Paragraph("11. Customers & accounts", s["h1"]))
    story.append(section_rule())
    story.append(
        bullets(
            [
                "Company-wide customers; types Regular / Family / Staff (cost-based pricing where configured).",
                "Deposit cash → account balance; pay order with payment_method=account.",
                "Cashier Customer Payment screen; printable statements.",
            ],
            s,
        )
    )

    # 12 Clients
    story.append(Paragraph("12. Client applications", s["h1"]))
    story.append(section_rule())
    story.append(Paragraph("Android kitchen / POS", s["h2"]))
    story.append(
        FlowBox(["config.json server", "mobile-login", "Kitchen poll + print", "POS / day-end"])
    )
    story.append(Paragraph("Desktop offline POS", s["h2"]))
    story.append(
        FlowBox(["desktop-login", "Pull catalog", "Local SQLite orders", "Sync push when online"])
    )
    story.append(
        Paragraph(
            "Sync: GET /api/sync/ping|pull/ · POST /api/sync/push/ · SyncedClientOrder UUID idempotency. "
            "Fiscal day remains online-only for managers.",
            s["small"],
        )
    )

    # 13 Navigation
    story.append(Paragraph("13. Main screens (web console)", s["h1"]))
    story.append(section_rule())
    story.append(
        simple_table(
            ["Screen", "Path", "Who"],
            [
                ["Dashboard", "/", "HQ / global"],
                ["Point of Sale", "/pos/", "POS roles"],
                ["Kitchen", "/kitchen/", "Kitchen access"],
                ["Orders / Invoices / Receipts", "/orders/ …", "Management / fiscal cashiers"],
                ["Stock Take / Adjust", "/stock-take/ …", "Management / cashier"],
                ["GRV", "/grv/", "Receive roles"],
                ["Bakery Production / Transfers", "/bakery-production/ …", "Bakery access"],
                ["Stores Transfers / Central Invoice", "/stores-transfers/ …", "Stores / HQ"],
                ["Purchases / Recipes / Catalog", "/purchase-orders/ …", "Capability gated"],
                ["Reports / Users / Payment rates", "/reports/ …", "Role gated"],
            ],
            col_widths=[55 * mm, 55 * mm, 60 * mm],
        )
    )

    story.append(PageBreak())

    # 14 E2E
    story.append(Paragraph("14. End-to-end master flows", s["h1"]))
    story.append(section_rule())
    story.append(Paragraph("A. Supply chain into café", s["h2"]))
    story.append(
        FlowBox(["Supplier", "Central Stores", "Bakery / Branch", "POS sale"])
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("B. Bakery finished goods path", s["h2"]))
    story.append(
        FlowBox(["Recipe + produce", "Bakery stock", "Delivery note", "Café stock → sell"])
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("C. Fiscal café trading day", s["h2"]))
    story.append(
        FlowBox(["Open fiscal day", "Orders → pay", "Approve fiscal", "Day-end + close"])
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("D. Wholesale", s["h2"]))
    story.append(FlowBox(["Stores stock", "Central Invoice", "Customer", "Mark paid"]))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Quick reference — one-liners", s["h2"]))
    story.append(
        bullets(
            [
                "<b>Buy raw goods:</b> Supplier → Purchase at Stores → BranchInventory (stores).",
                "<b>Feed bakery:</b> Ingredients at bakery → Production → Finished bakery stock.",
                "<b>Supply café:</b> Bakery DN and/or Stores DN → Café inventory → POS sale (recipe or finished SKU).",
                "<b>Fiscalise:</b> Pay → proforma → manager approve → ZIMRA → fiscal receipt.",
                "<b>Wholesale:</b> Central Invoice → external customer → stock out.",
                "<b>Cash control:</b> Sales + deposits − expenses → DayEndClose (after daily stock take).",
            ],
            s,
        )
    )

    story.append(Spacer(1, 12 * mm))
    story.append(section_rule())
    story.append(
        Paragraph(
            "This document mirrors live behaviour in accounts/branch_access.py, orders/services.py, "
            "inventory/services.py, bakery/services.py, zimra_fiscal/, and ui/urls.py. "
            "Regenerate with: python docs/generate_process_flow_pdf.py",
            s["small"],
        )
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Café de Paris — Application Process Flow",
        author="Café de Paris",
    )
    doc.build(story, onFirstPage=_cover_page, onLaterPages=add_header_footer)
    print(f"Wrote {OUT}")


def _cover_page(canvas, doc):
    canvas.saveState()
    # cover accent bar
    canvas.setFillColor(BRAND)
    canvas.rect(0, 0, 8 * mm, A4[1], fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(8 * mm, 0, 2 * mm, A4[1], fill=1, stroke=0)
    canvas.restoreState()


if __name__ == "__main__":
    build()
