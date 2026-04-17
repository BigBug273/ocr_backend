import re

from ...schemas import ParsedReceipt, ReceiptItemCreate
from .common import (
    build_parsed_receipt,
    clean_amount,
    extract_company_name,
    extract_tax_id,
    extract_total,
    find_item_zone_lines,
    is_likely_address_or_header,
    maybe_item_name,
    normalize_spaces,
)


def _dedupe_items(items: list[ReceiptItemCreate]) -> list[ReceiptItemCreate]:
    deduped: list[ReceiptItemCreate] = []
    seen = set()

    for item in items:
        signature = (
            (item.item_name or "").lower(),
            item.qty,
            item.unit_price,
            item.line_total,
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)

    return deduped


def _extract_items_from_lines(lines: list[str], grand_total: float | None = None) -> list[ReceiptItemCreate]:
    items: list[ReceiptItemCreate] = []

    pattern_name_qty_unit_total = re.compile(
        r"^(?P<name>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s*[x×]\s*(?P<unit>\d+(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:=)?\s*(?P<total>\d+(?:,\d{3})*(?:\.\d{1,2})?)$",
        flags=re.IGNORECASE,
    )
    pattern_name_qty_unit_total_no_x = re.compile(
        r"^(?P<name>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+(?P<unit>\d+(?:,\d{3})*(?:\.\d{1,2})?)\s+(?P<total>\d+(?:,\d{3})*(?:\.\d{1,2})?)$",
        flags=re.IGNORECASE,
    )
    pattern_qty_name_total = re.compile(
        r"^(?P<qty>\d+(?:\.\d+)?)\s+(?P<name>.+?)\s+(?P<total>\d+(?:,\d{3})*(?:\.\d{1,2})?)$",
        flags=re.IGNORECASE,
    )

    for line in lines:
        line = normalize_spaces(line)
        if not line or is_likely_address_or_header(line):
            continue

        parsed_item: ReceiptItemCreate | None = None

        m = pattern_name_qty_unit_total.match(line)
        if m:
            name = normalize_spaces(m.group("name"))
            if maybe_item_name(name):
                qty = clean_amount(m.group("qty"))
                unit_price = clean_amount(m.group("unit"))
                line_total = clean_amount(m.group("total"))
                if qty is not None and unit_price is not None and line_total is not None:
                    parsed_item = ReceiptItemCreate(
                        item_name=name,
                        qty=qty,
                        unit_price=unit_price,
                        line_total=line_total,
                    )

        if parsed_item is None:
            m = pattern_name_qty_unit_total_no_x.match(line)
            if m:
                name = normalize_spaces(m.group("name"))
                if maybe_item_name(name):
                    qty = clean_amount(m.group("qty"))
                    unit_price = clean_amount(m.group("unit"))
                    line_total = clean_amount(m.group("total"))
                    if qty is not None and unit_price is not None and line_total is not None:
                        parsed_item = ReceiptItemCreate(
                            item_name=name,
                            qty=qty,
                            unit_price=unit_price,
                            line_total=line_total,
                        )

        if parsed_item is None:
            m = pattern_qty_name_total.match(line)
            if m:
                qty = clean_amount(m.group("qty"))
                name = normalize_spaces(m.group("name"))
                line_total = clean_amount(m.group("total"))

                if qty and line_total is not None and maybe_item_name(name):
                    unit_price = round(line_total / qty, 2)
                    parsed_item = ReceiptItemCreate(
                        item_name=name,
                        qty=qty,
                        unit_price=unit_price,
                        line_total=line_total,
                    )

        if parsed_item is not None:
            items.append(parsed_item)

    items = _dedupe_items(items)

    if grand_total is not None and items:
        exact_total_items = [
            item for item in items
            if item.line_total is not None and abs(item.line_total - grand_total) < 0.01
        ]
        if exact_total_items:
            return exact_total_items

    return items


def _extract_items_from_text(text: str, grand_total: float | None = None) -> list[ReceiptItemCreate]:
    items: list[ReceiptItemCreate] = []
    compact = normalize_spaces(text)

    # พยายามตัดข้อความให้เหลือช่วง item table ก่อน
    table_segment = compact
    table_start_match = re.search(
        r"(?:#\s*)?รายละเอียด\s+จำนวน\s+ราคาต่อหน่วย\s+ส่วนลด\s+มูลค่า\s+",
        compact,
        flags=re.IGNORECASE,
    )
    if table_start_match:
        table_segment = compact[table_start_match.end():]

    # ตัดก่อนเข้า summary
    table_end_match = re.search(
        r"(รวมเป็นเงิน|รวมทั้งสิ้น|ยอดรวมสุทธิ|ภาษีมูลค่าเพิ่ม|vat included)",
        table_segment,
        flags=re.IGNORECASE,
    )
    if table_end_match:
        table_segment = table_segment[:table_end_match.start()]

    # รูปแบบหลักของใบเต็ม:
    # 1 เมล็ดกาแฟคั่วเข้ม 500 ถุง 50 250.00 5 % 11,875.00
    pattern_invoice_row = re.compile(
        r"(?:^|\s)"
        r"(?P<row_no>\d+)\s+"
        r"(?P<name>.+?)\s+"
        r"(?P<qty>\d+(?:\.\d+)?)\s+"
        r"(?P<unit>\d+(?:,\d{3})*(?:\.\d{1,2})?)\s+"
        r"(?:(?P<discount>\d+(?:\.\d+)?)\s*%?\s+)?"
        r"(?P<total>\d+(?:,\d{3})*(?:\.\d{1,2})?)"
        r"(?=\s|$)",
        flags=re.IGNORECASE,
    )

    for match in pattern_invoice_row.finditer(table_segment):
        row_no = match.group("row_no")
        name = normalize_spaces(match.group("name") or "")
        qty = clean_amount(match.group("qty"))
        unit_price = clean_amount(match.group("unit"))
        line_total = clean_amount(match.group("total"))

        if not name or not maybe_item_name(name):
            continue
        if qty is None or unit_price is None or line_total is None:
            continue

        # กันค่าที่หลุดผิดบริบท
        if grand_total is not None:
            if line_total > grand_total * 2:
                continue
            if unit_price > grand_total:
                continue

        items.append(
            ReceiptItemCreate(
                item_name=name,
                qty=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    items = _dedupe_items(items)

    if grand_total is not None and items:
        exact_total_items = [
            item for item in items
            if item.line_total is not None and abs(item.line_total - grand_total) < 0.01
        ]
        if exact_total_items:
            return exact_total_items

    return items


def parse_full_invoice(filename: str, text: str, lines: list[str]) -> ParsedReceipt:

    company_name = extract_company_name(lines)
    tax_id = extract_tax_id(text)
    grand_total = extract_total(text, lines)

    zone_lines = find_item_zone_lines(lines)

    candidates: list[ReceiptItemCreate] = []

    # 1) ลองจาก text ทั้งก้อนก่อน เพราะเคส invoice เต็มรูป OCR มักรวมบรรทัดตารางเป็นข้อความยาว
    candidates.extend(_extract_items_from_text(text, grand_total=grand_total))

    # 2) ลองจาก item zone
    zone_candidates = _extract_items_from_lines(zone_lines, grand_total=grand_total)
    for item in zone_candidates:
        candidates.append(item)

    # 3) fallback ทั้งเอกสาร
    line_candidates = _extract_items_from_lines(lines, grand_total=grand_total)
    for item in line_candidates:
        candidates.append(item)

    candidates = _dedupe_items(candidates)

    if grand_total is not None and candidates:
        exact_total_items = [
            item for item in candidates
            if item.line_total is not None and abs(item.line_total - grand_total) < 0.01
        ]
        if exact_total_items:
            candidates = exact_total_items

    return build_parsed_receipt(
        filename=filename,
        cleaned_text=text,
        company_name=company_name,
        tax_id=tax_id,
        grand_total=grand_total,
        items=candidates,
    )
