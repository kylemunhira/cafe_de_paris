import csv
import io
from decimal import Decimal, InvalidOperation

from .models import StockTake, StockTakeStatus
from .services import InvalidStockTakeStateError, update_stock_take_lines

CSV_HEADERS = [
    "line_id",
    "category",
    "product_name",
    "counted_quantity",
]

REPORT_CSV_HEADERS = [
    "line_id",
    "category",
    "product_name",
    "system_quantity",
    "counted_quantity",
    "variance",
]


def export_stock_take_csv(stock_take: StockTake) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()
    for line in stock_take.lines.select_related("product__category"):
        writer.writerow(
            {
                "line_id": line.id,
                "category": line.product.category.name,
                "product_name": line.product.name,
                "counted_quantity": line.counted_quantity if line.counted_quantity is not None else "",
            }
        )
    return output.getvalue()


def export_stock_take_report_csv(stock_take: StockTake) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=REPORT_CSV_HEADERS)
    writer.writeheader()
    for line in stock_take.lines.select_related("product__category"):
        variance = line.variance
        writer.writerow(
            {
                "line_id": line.id,
                "category": line.product.category.name,
                "product_name": line.product.name,
                "system_quantity": line.system_quantity,
                "counted_quantity": line.counted_quantity if line.counted_quantity is not None else "",
                "variance": variance if variance is not None else "",
            }
        )
    return output.getvalue()


def _parse_decimal(value, field_name, *, required=False, min_value=None):
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"{field_name} is required")
        return None
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc
    if min_value is not None and amount < min_value:
        raise ValueError(f"{field_name} must be {min_value} or greater")
    return amount


def import_stock_take_csv(stock_take: StockTake, file_obj):
    if stock_take.status != StockTakeStatus.DRAFT:
        raise InvalidStockTakeStateError(
            stock_take, StockTakeStatus.DRAFT, "import CSV"
        )

    try:
        text = io.TextIOWrapper(file_obj, encoding="utf-8-sig")
        reader = csv.DictReader(text)
    except UnicodeDecodeError:
        return {"updated": 0, "errors": [{"row": 0, "message": "File must be UTF-8 encoded CSV"}]}

    if not reader.fieldnames:
        return {"updated": 0, "errors": [{"row": 0, "message": "CSV file is empty"}]}

    normalized_headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    if "counted_quantity" not in normalized_headers:
        return {
            "updated": 0,
            "errors": [{"row": 0, "message": "Missing required column: counted_quantity"}],
        }
    if "line_id" not in normalized_headers and "product_id" not in normalized_headers:
        return {
            "updated": 0,
            "errors": [{"row": 0, "message": "Missing required column: line_id or product_id"}],
        }

    line_by_id = {line.id: line for line in stock_take.lines.all()}
    line_by_product = {line.product_id: line for line in stock_take.lines.all()}

    lines_data = []
    errors = []

    for row_num, row in enumerate(reader, start=2):
        if not any(str(v).strip() for v in row.values() if v is not None):
            continue

        try:
            line_id_raw = str(row.get(normalized_headers.get("line_id", ""), "")).strip()
            product_id_raw = str(
                row.get(normalized_headers.get("product_id", ""), "")
            ).strip()

            line = None
            if line_id_raw:
                try:
                    line = line_by_id.get(int(line_id_raw))
                except ValueError as exc:
                    raise ValueError(f"invalid line_id: {line_id_raw!r}") from exc
                if line is None:
                    raise ValueError(f"line_id {line_id_raw!r} not found in this stock take")
            elif product_id_raw:
                try:
                    line = line_by_product.get(int(product_id_raw))
                except ValueError as exc:
                    raise ValueError(f"invalid product_id: {product_id_raw!r}") from exc
                if line is None:
                    raise ValueError(
                        f"product_id {product_id_raw!r} not found in this stock take"
                    )
            else:
                raise ValueError("line_id or product_id is required")

            counted_quantity = _parse_decimal(
                row.get(normalized_headers.get("counted_quantity", "counted_quantity")),
                "counted_quantity",
                min_value=Decimal("0"),
            )
            notes_header = normalized_headers.get("notes")
            notes = str(row.get(notes_header, "")).strip() if notes_header else ""

            entry = {"id": line.id}
            if counted_quantity is not None:
                entry["counted_quantity"] = counted_quantity
            if notes_header:
                entry["notes"] = notes
            lines_data.append(entry)
        except Exception as exc:
            errors.append({"row": row_num, "message": str(exc)})

    if errors:
        return {"updated": 0, "errors": errors}

    if not lines_data:
        return {"updated": 0, "errors": [{"row": 0, "message": "No data rows found in CSV"}]}

    update_stock_take_lines(stock_take, lines_data)
    return {"updated": len(lines_data), "errors": []}
