"""Collect missing msgids and append translated _add() entries to i18n_catalog.py."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(r"c:\Users\HP\Documents\GitHub\cafe_de_paris")
CATALOG = ROOT / "ui" / "i18n_catalog.py"


def extract_msgids(text: str) -> set[str]:
    found: set[str] = set()
    for pat in (
        r"""\{%\s*trans\s+"((?:\\.|[^"\\])*)"\s*%\}""",
        r"""\{%\s*trans\s+'((?:\\.|[^'\\])*)'\s*%\}""",
        r"""\bt\(\s*"((?:\\.|[^"\\])*)"\s*\)""",
        r"""\bt\(\s*'((?:\\.|[^'\\])*)'\s*\)""",
    ):
        for m in re.finditer(pat, text):
            raw = m.group(1)
            try:
                found.add(ast.literal_eval('"' + raw.replace('"', '\\"') + '"') if "\\" in raw else raw)
            except Exception:
                found.add(raw)
    return found


def py_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


# Manual high-quality translations for new UI strings.
# Missing keys fall back to English in all languages (still registered).
TR: dict[str, tuple[str, str, str, str]] = {
    "(optional)": ("(facultatif)", "(opcional)", "(اختياري)", "（可选）"),
    "Account balance": ("Solde du compte", "Saldo de la cuenta", "رصيد الحساب", "账户余额"),
    "Action failed.": ("Échec de l'action.", "La acción falló.", "فشل الإجراء.", "操作失败。"),
    "Active count": ("Comptage actif", "Conteo activo", "الجرد النشط", "进行中的盘点"),
    "Active production": ("Production active", "Producción activa", "الإنتاج النشط", "进行中的生产"),
    "Actual wastage/disposal": ("Pertes / mise au rebut", "Merma / desecho real", "هدر/تخلص فعلي", "实际损耗/报废"),
    "Add amounts to current stock": ("Ajouter au stock actuel", "Sumar al stock actual", "إضافة إلى المخزون الحالي", "加到当前库存"),
    "Add at least one product": ("Ajoutez au moins un produit", "Añada al menos un producto", "أضف منتجاً واحداً على الأقل", "请至少添加一个产品"),
    "Add at least one product line": ("Ajoutez au moins une ligne", "Añada al menos una línea", "أضف بند منتج واحداً على الأقل", "请至少添加一行产品"),
    "Add expense": ("Ajouter une dépense", "Agregar gasto", "إضافة مصروف", "添加费用"),
    "Add ingredient": ("Ajouter un ingrédient", "Agregar ingrediente", "إضافة مكون", "添加原料"),
    "Add line": ("Ajouter une ligne", "Agregar línea", "إضافة بند", "添加行"),
    "Add product": ("Ajouter un produit", "Agregar producto", "إضافة منتج", "添加产品"),
    "Add qty": ("Qté à ajouter", "Cant. a sumar", "كمية الإضافة", "加数量"),
    "Add table": ("Ajouter une table", "Agregar mesa", "إضافة طاولة", "添加桌台"),
    "Add to cart": ("Ajouter au panier", "Agregar al carrito", "أضف إلى السلة", "加入购物车"),
    "Adjust balance": ("Ajuster le solde", "Ajustar saldo", "تعديل الرصيد", "调整余额"),
    "Adjustment amount": ("Montant de l'ajustement", "Importe del ajuste", "مبلغ التعديل", "调整金额"),
    "All purchases": ("Tous les achats", "Todas las compras", "جميع المشتريات", "全部采购"),
    "All reasons": ("Toutes les raisons", "Todos los motivos", "جميع الأسباب", "全部原因"),
    "All statuses": ("Tous les statuts", "Todos los estados", "جميع الحالات", "全部状态"),
    "All transactions": ("Toutes les transactions", "Todas las transacciones", "جميع المعاملات", "全部交易"),
    "Amount must be a positive number": ("Le montant doit être positif", "El importe debe ser positivo", "يجب أن يكون المبلغ موجباً", "金额必须为正数"),
    "Amount paid": ("Montant payé", "Importe pagado", "المبلغ المدفوع", "已付金额"),
    "Amount received": ("Montant reçu", "Importe recibido", "المبلغ المستلم", "收到金额"),
    "Amount tendered": ("Montant remis", "Importe entregado", "المبلغ المقدم", "实收金额"),
    "Amt": ("Mnt", "Imp.", "المبلغ", "金额"),
    "Apply adjustment": ("Appliquer l'ajustement", "Aplicar ajuste", "تطبيق التعديل", "应用调整"),
    "Apply all filled": ("Appliquer les lignes remplies", "Aplicar todas las completadas", "تطبيق جميع المعبأة", "应用所有已填"),
    "Approved": ("Approuvé", "Aprobado", "موافق عليه", "已批准"),
    "Available": ("Disponible", "Disponible", "المتاح", "可用"),
    "Awaiting receipt": ("En attente de réception", "En espera de recepción", "بانتظار الاستلام", "待收货"),
    "Bakery": ("Boulangerie", "Panadería", "المخبز", "烘焙"),
    "Bakery destination": ("Destination boulangerie", "Destino panadería", "وجهة المخبز", "烘焙目的地"),
    "Bakery transfers": ("Transferts boulangerie", "Transferencias de panadería", "تحويلات المخبز", "烘焙调拨"),
}


def main() -> None:
    ns: dict = {}
    exec(CATALOG.read_text(encoding="utf-8"), ns)
    existing = set(ns["TRANSLATIONS"].keys())

    all_msgids: set[str] = set()
    for path in (ROOT / "ui/templates/ui").rglob("*.html"):
        all_msgids |= extract_msgids(path.read_text(encoding="utf-8"))

    missing = sorted(m for m in all_msgids if m and m not in existing)
    (ROOT / "scripts/_i18n_missing_only.txt").write_text("\n".join(missing), encoding="utf-8")
    print(f"missing={len(missing)} written")

    lines = ["\n# --- Inventory / transfers / POS / statements / print (auto-appended) ---\n"]
    for msgid in missing:
        fr, es, ar, zh = TR.get(msgid, (msgid, msgid, msgid, msgid))
        lines.append(
            f"_add({py_str(msgid)}, {py_str(fr)}, {py_str(es)}, {py_str(ar)}, {py_str(zh)})\n"
        )

    text = CATALOG.read_text(encoding="utf-8")
    marker = "\nMSGIDS = list(TRANSLATIONS.keys())\n"
    if marker not in text:
        raise SystemExit("MSGIDS marker not found")
    if "# --- Inventory / transfers / POS / statements / print (auto-appended) ---" in text:
        print("already appended; skip")
        return
    text = text.replace(marker, "".join(lines) + marker)
    CATALOG.write_text(text, encoding="utf-8")
    print(f"appended {len(missing)} entries (fallback EN where untranslated map missing)")


if __name__ == "__main__":
    main()
