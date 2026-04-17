import re

from ...schemas import ParsedReceipt, ReceiptItemCreate
from .common import (
    build_parsed_receipt,
    clean_amount,
    extract_company_name,
    extract_tax_id,
    extract_total,
    maybe_item_name,
    normalize_spaces,
)


def _extract_short_receipt_items(lines: list[str], grand_total: float | None) -> list[ReceiptItemCreate]:
    items: list[ReceiptItemCreate] = []
    seen = set()

    pattern_qty_name_total = re.compile(
        r"^(?P<qty>\d+(?:\.\d+)?)\s+(?P<name>.+?)\s+(?P<total>\d+(?:,\d{3})*(?:\.\d{1,2})?)$",
        flags=re.IGNORECASE,
    )

    pattern_name_total = re.compile(
        r"^(?P<name>[^\d].*?)\s+(?P<total>\d+(?:,\d{3})*(?:\.\d{1,2})?)$",
        flags=re.IGNORECASE,
    )

    for line in lines:
        line = normalize_spaces(line)
        if not line:
            continue

        m = pattern_qty_name_total.match(line)
        if m:
            qty = clean_amount(m.group("qty"))
            name = normalize_spaces(m.group("name"))
            line_total = clean_amount(m.group("total"))

            if qty and line_total is not None and maybe_item_name(name):
                unit_price = round(line_total / qty, 2)
                sig = (name.lower(), qty, unit_price, line_total)
                if sig not in seen:
                    seen.add(sig)
                    items.append(
                        ReceiptItemCreate(
                            item_name=name,
                            qty=qty,
                            unit_price=unit_price,
                            line_total=line_total,
                        )
                    )
                continue

        m = pattern_name_total.match(line)
        if m:
            name = normalize_spaces(m.group("name"))
            line_total = clean_amount(m.group("total"))

            if line_total is not None and maybe_item_name(name):
                if grand_total is not None and line_total < grand_total * 0.5:
                    continue
                sig = (name.lower(), 1.0, line_total, line_total)
                if sig not in seen:
                    seen.add(sig)
                    items.append(
                        ReceiptItemCreate(
                            item_name=name,
                            qty=1.0,
                            unit_price=line_total,
                            line_total=line_total,
                        )
                    )

    if grand_total is not None and items:
        exact_total_items = [
            item for item in items
            if item.line_total is not None and abs(item.line_total - grand_total) < 0.01
        ]
        if len(exact_total_items) == 1:
            return exact_total_items

    return items


def parse_short_receipt(filename: str, text: str, lines: list[str]) -> ParsedReceipt:
    company_name = extract_company_name(lines)
    tax_id = extract_tax_id(text)
    grand_total = extract_total(text, lines)
    items = _extract_short_receipt_items(lines, grand_total)

    return build_parsed_receipt(
        filename=filename,
        cleaned_text=text,
        company_name=company_name,
        tax_id=tax_id,
        grand_total=grand_total,
        items=items,
    )