import re

from ...schemas import ParsedReceipt, ReceiptItemCreate
from .common import (
    build_parsed_receipt,
    clean_amount,
    extract_company_name,
    extract_tax_id,
    extract_total,
    normalize_spaces,
)


def _extract_cash_bill_items(lines: list[str], grand_total: float | None) -> list[ReceiptItemCreate]:
    items: list[ReceiptItemCreate] = []

    # เคสเขียนมือแบบ:
    # 50 เมล็ดกาแฟคั่วเข้ม 250 12,500
    pattern = re.compile(
        r"^(?P<qty>\d+(?:\.\d+)?)\s+(?P<name>.+?)\s+(?P<unit>\d+(?:,\d{3})*(?:\.\d{1,2})?)\s+(?P<total>\d+(?:,\d{3})*(?:\.\d{1,2})?)$",
        flags=re.IGNORECASE,
    )

    for line in lines:
        line = normalize_spaces(line)
        if not line:
            continue

        m = pattern.match(line)
        if not m:
            continue

        qty = clean_amount(m.group("qty"))
        name = normalize_spaces(m.group("name"))
        unit_price = clean_amount(m.group("unit"))
        line_total = clean_amount(m.group("total"))

        if qty is None or unit_price is None or line_total is None:
            continue

        items.append(
            ReceiptItemCreate(
                item_name=name,
                qty=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    if grand_total is not None and items:
        exact_total_items = [
            item for item in items
            if item.line_total is not None and abs(item.line_total - grand_total) < 0.01
        ]
        if exact_total_items:
            return exact_total_items

    return items


def parse_cash_bill(filename: str, text: str, lines: list[str]) -> ParsedReceipt:
    company_name = extract_company_name(lines)
    tax_id = extract_tax_id(text)
    grand_total = extract_total(text, lines)
    items = _extract_cash_bill_items(lines, grand_total)

    return build_parsed_receipt(
        filename=filename,
        cleaned_text=text,
        company_name=company_name,
        tax_id=tax_id,
        grand_total=grand_total,
        items=items,
        force_review=True,  # เขียนมือให้ review ไว้ก่อน
    )