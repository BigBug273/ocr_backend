import re
from typing import List

from ...schemas import ParsedReceipt, ReceiptItemCreate

TOTAL_KEYWORDS_PRIORITY = [
    "รวมทั้งสิ้น",
    "ยอดรวมสุทธิ",
    "รวมสุทธิ",
    "ยอดสุทธิ",
    "grand total",
    "net total",
    "total due",
    "amount due",
]

TOTAL_KEYWORDS_FALLBACK = [
    "รวม",
    "สุทธิ",
    "total",
]

EXCLUDED_COMPANY_KEYWORDS = {
    "tax",
    "vat",
    "ใบเสร็จ",
    "receipt",
    "branch",
    "tel",
    "phone",
    "cashier",
    "pos",
    "invoice",
    "table",
    "qty",
    "ราคา",
    "จำนวน",
    "รวม",
    "total",
    "วันที่",
    "พนักงานขาย",
    "customer",
    "address",
}

ITEM_EXCLUDE_KEYWORDS = [
    "เลขผู้เสียภาษี",
    "เลขประจำตัวผู้เสียภาษี",
    "เลขประจำตัวภาษี",
    "โทร",
    "โทร.",
    "วันที่",
    "พนักงานขาย",
    "ใบกำกับภาษี",
    "ใบเสร็จรับเงิน",
    "รวมเป็นเงิน",
    "ส่วนลด",
    "จำนวนเงินหลังหักส่วนลด",
    "ราคาไม่รวมภาษีมูลค่าเพิ่ม",
    "ภาษีมูลค่าเพิ่ม",
    "รวมทั้งสิ้น",
    "ยอดรวมสุทธิ",
    "รวมสุทธิ",
    "vat included",
    "vat",
    "tax",
    "cash",
    "change",
    "เงินทอน",
    "service",
    "กรุงเทพมหานคร",
    "customer",
    "address",
    "date",
    "credit",
    "ครบกำหนด",
    "ผู้ขาย",
    "ลูกค้า",
    "ชื่อผู้ติดต่อ",
    "เบอร์โทร",
    "อีเมล",
    "ชำระเงิน",
    "ธนาคาร",
    "ผู้รับเงิน",
    "ผู้จ่ายเงิน",
]

PROVINCE_HINTS = [
    "กรุงเทพมหานคร",
    "เขต",
    "แขวง",
    "อำเภอ",
    "ตำบล",
    "จังหวัด",
    "ถนน",
    "ซอย",
]

SUMMARY_STOP_KEYWORDS = [
    "รวมเป็นเงิน",
    "รวมทั้งสิ้น",
    "ยอดรวมสุทธิ",
    "รวมสุทธิ",
    "ภาษีมูลค่าเพิ่ม",
    "vat included",
    "ชำระเงิน",
    "ธนาคาร",
    "ผู้รับเงิน",
    "ผู้จ่ายเงิน",
]

ITEM_ZONE_HINTS = [
    "รายละเอียด",
    "description",
    "รายการ",
    "qty",
    "quantity",
    "ราคาต่อหน่วย",
    "unit price",
    "มูลค่า",
    "amount",
]

HTML_TAG_RE = re.compile(r"<[^>]+>")
MULTISPACE_RE = re.compile(r"[ \t]+")
NUMBER_RE = re.compile(r"([0-9][0-9,]*\.?[0-9]{0,2})")


def normalize_spaces(text: str) -> str:
    return MULTISPACE_RE.sub(" ", text).strip()


def strip_html(text: str) -> str:
    text = HTML_TAG_RE.sub(" ", text)
    text = text.replace("\\n", "\n").replace("\\t", " ")
    return text


def clean_amount(raw: str) -> float | None:
    cleaned = raw.replace(",", "").replace("฿", "").strip()
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    if cleaned.count(".") > 1:
        parts = cleaned.split(".")
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def is_noise_line(line: str) -> bool:
    lowered = line.lower()
    if not line:
        return True
    if line in {"-", "--", "---", "----"}:
        return True
    if re.fullmatch(r"[-=_. ]+", line):
        return True
    if any(tag in lowered for tag in ["<table", "<tr", "<td", "</table", "</tr", "</td"]):
        return True
    return False


def prepare_lines(text: str) -> tuple[str, list[str]]:
    cleaned = strip_html(text)
    raw_lines = re.split(r"[\r\n]+", cleaned)
    lines: list[str] = []

    for line in raw_lines:
        line = normalize_spaces(line)
        if is_noise_line(line):
            continue
        lines.append(line)

    return cleaned, lines


def extract_company_name(lines: List[str]) -> str | None:
    for line in lines[:10]:
        cleaned = normalize_spaces(line)
        lowered = cleaned.lower()

        if not cleaned or len(cleaned) < 2:
            continue
        if any(keyword in lowered for keyword in EXCLUDED_COMPANY_KEYWORDS):
            continue
        if re.fullmatch(r"[0-9\-:/ .]+", cleaned):
            continue
        return cleaned
    return None


def extract_tax_id(text: str) -> str | None:
    patterns = [
        r"(?:tax\s*id|taxid|tax\s*no\.?|เลขประจำตัวผู้เสียภาษี|เลขผู้เสียภาษี|เลขประจำตัวภาษี)\s*[:\-]?\s*([0-9\-]{10,17})",
        r"\b([0-9]{13})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            digits = re.sub(r"\D", "", match.group(1))
            if 10 <= len(digits) <= 13:
                return digits
    return None


def extract_total(text: str, lines: List[str]) -> float | None:
    priority_candidates: list[float] = []

    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in TOTAL_KEYWORDS_PRIORITY):
            amounts = NUMBER_RE.findall(line)
            if amounts:
                value = clean_amount(amounts[-1])
                if value is not None:
                    priority_candidates.append(value)

    if priority_candidates:
        return priority_candidates[-1]

    fallback_candidates: list[float] = []

    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in TOTAL_KEYWORDS_FALLBACK):
            if any(
                bad in lowered
                for bad in [
                    "vat",
                    "ภาษีมูลค่าเพิ่ม",
                    "ส่วนลด",
                    "discount",
                    "ราคาไม่รวม",
                    "ก่อนภาษี",
                ]
            ):
                continue

            amounts = NUMBER_RE.findall(line)
            if amounts:
                value = clean_amount(amounts[-1])
                if value is not None:
                    fallback_candidates.append(value)

    if fallback_candidates:
        return fallback_candidates[-1]

    for keyword in TOTAL_KEYWORDS_PRIORITY + TOTAL_KEYWORDS_FALLBACK:
        pattern = rf"{re.escape(keyword)}\s*[:=]?\s*([0-9][0-9,]*\.?[0-9]{{0,2}})"
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            value = clean_amount(matches[-1])
            if value is not None:
                return value

    return None


def is_likely_address_or_header(line: str) -> bool:
    lowered = line.lower()

    if any(keyword.lower() in lowered for keyword in ITEM_EXCLUDE_KEYWORDS):
        return True

    if any(hint in line for hint in PROVINCE_HINTS):
        return True

    if re.search(r"\b\d{13}\b", line):
        return True
    if re.search(r"\b\d{2}/\d{2}/\d{4}\b", line):
        return True

    digits_only = re.sub(r"[^\d]", "", line)
    if re.search(r"0\d{8,9}", digits_only):
        return True

    return False


def maybe_item_name(name: str) -> bool:
    lowered = name.lower().strip()

    if len(lowered) < 2:
        return False
    if any(keyword in lowered for keyword in TOTAL_KEYWORDS_PRIORITY + TOTAL_KEYWORDS_FALLBACK):
        return False
    if is_likely_address_or_header(name):
        return False

    return True


def find_item_zone_lines(lines: list[str]) -> list[str]:
    start_idx = None
    end_idx = len(lines)

    for i, line in enumerate(lines):
        lowered = line.lower()
        if any(hint in lowered for hint in ITEM_ZONE_HINTS):
            start_idx = i + 1
            break

    if start_idx is None:
        return lines

    for j in range(start_idx, len(lines)):
        lowered = lines[j].lower()
        if any(stop in lowered for stop in SUMMARY_STOP_KEYWORDS):
            end_idx = j
            break

    zone = lines[start_idx:end_idx]
    return [line for line in zone if not is_likely_address_or_header(line)]


def build_parsed_receipt(
    filename: str,
    cleaned_text: str,
    company_name: str | None,
    tax_id: str | None,
    grand_total: float | None,
    items: list[ReceiptItemCreate],
    success: bool = True,
    error: str | None = None,
    force_review: bool = False,
) -> ParsedReceipt:
    needs_review = force_review or not (company_name and grand_total is not None) or len(items) == 0

    return ParsedReceipt(
        filename=filename,
        success=success,
        company_name=company_name,
        tax_id=tax_id,
        grand_total=grand_total,
        raw_text=cleaned_text,
        needs_review=needs_review,
        items=items,
        error=error,
    )