import json
import os
import re
import time
from typing import Any

from ...schemas import ParsedReceipt, ReceiptItemCreate

try:
    from google import genai
except ImportError:
    genai = None


def _extract_json_block(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None

    return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
        if cleaned.count(".") > 1:
            parts = cleaned.split(".")
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            return float(cleaned)
        except Exception:
            return None

    return None


def _clean_item_name(name: str) -> str:
    if not name:
        return ""

    cleaned = name.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+\d+$", "", cleaned)
    cleaned = cleaned.strip(" -_,.;:")
    return cleaned.strip()


def _looks_like_bad_item_name(name: str) -> bool:
    if not name:
        return True

    lowered = name.lower().strip()

    suspicious_keywords = [
        "แขวง", "เขต", "จังหวัด", "ถนน", "ซอย", "โทร", "โทรสาร", "เลขที่",
        "หมายเหตุ", "ผู้รับเงิน", "ผู้มีอำนาจลงนาม", "จัดเตรียมโดย", "ตรวจสอบโดย",
        "ชำระโดย", "เงินสด", "เช็ค", "ธนาคาร", "หน้า", "ยอดคงค้าง", "ยอดชำระ",
        "รวมเป็นเงิน", "จำนวนเงินทั้งสิ้น", "grand total", "discount",
        "vat included", "signature", "handwritten signature",
    ]

    if any(keyword in lowered for keyword in suspicious_keywords):
        return True

    if len(lowered) < 3:
        return True

    if re.fullmatch(r"[\d\W_]+", lowered):
        return True

    return False


def _normalize_items(items_data: Any) -> list[ReceiptItemCreate]:
    if not isinstance(items_data, list):
        return []

    normalized: list[ReceiptItemCreate] = []

    for item in items_data:
        if not isinstance(item, dict):
            continue

        item_name = _clean_item_name(str(item.get("item_name", "")).strip())
        if not item_name:
            continue

        if _looks_like_bad_item_name(item_name):
            continue

        qty = _safe_float(item.get("qty"))
        unit_price = _safe_float(item.get("unit_price"))
        line_total = _safe_float(item.get("line_total"))

        normalized.append(
            ReceiptItemCreate(
                item_name=item_name,
                qty=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    return normalized


def parse_with_llm_fallback(filename: str, raw_text: str, detected_doc_type: str = "unknown") -> ParsedReceipt:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if not api_key:
        return ParsedReceipt(
            filename=filename,
            success=True,
            doc_type=detected_doc_type,
            raw_text=raw_text,
            needs_review=True,
            items=[],
            error="LLM fallback skipped: GEMINI_API_KEY or GOOGLE_API_KEY is not set.",
        )

    if genai is None:
        return ParsedReceipt(
            filename=filename,
            success=True,
            doc_type=detected_doc_type,
            raw_text=raw_text,
            needs_review=True,
            items=[],
            error="LLM fallback skipped: google-genai package is not installed.",
        )

    prompt = f"""
You are a receipt and invoice extraction assistant.

Extract structured data from OCR text.

Rules:
1. Return ONLY valid JSON.
2. Do not include markdown, comments, or explanations.
3. If a field is not found, use null.
4. If the document is not a normal retail receipt/invoice, still try your best.
5. Items should only contain actual product/service/line items.
6. DO NOT use addresses, signatures, payment notes, summary lines, total lines, or company header lines as items.
7. Clean item names so they do not end with unrelated running numbers.

JSON schema:
{{
  "doc_type": "short_receipt | full_invoice | cash_bill_handwritten | statement_like | unknown",
  "company_name": string or null,
  "tax_id": string or null,
  "grand_total": number or null,
  "items": [
    {{
      "item_name": string,
      "qty": number or null,
      "unit_price": number or null,
      "line_total": number or null
    }}
  ]
}}

Detected doc type from rule-based system: {detected_doc_type}

OCR text:
{raw_text}
""".strip()

    try:
        client = genai.Client(api_key=api_key)

        response_text = None
        last_exception = None

        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                response_text = getattr(response, "text", None)
                break
            except Exception as exc:
                last_exception = exc
                error_text = str(exc)

                if "503" in error_text or "UNAVAILABLE" in error_text:
                    if attempt < 2:
                        wait_seconds = attempt + 2
                        time.sleep(wait_seconds)
                        continue
                    return ParsedReceipt(
                        filename=filename,
                        success=True,
                        doc_type=detected_doc_type,
                        raw_text=raw_text,
                        needs_review=True,
                        items=[],
                        error="LLM fallback temporarily unavailable. Using rule-based result.",
                    )

                raise

        if response_text is None:
            return ParsedReceipt(
                filename=filename,
                success=True,
                doc_type=detected_doc_type,
                raw_text=raw_text,
                needs_review=True,
                items=[],
                error=f"LLM fallback failed: {last_exception}",
            )

        parsed_json = _extract_json_block(response_text or "")

        if not parsed_json:
            return ParsedReceipt(
                filename=filename,
                success=True,
                doc_type=detected_doc_type,
                raw_text=raw_text,
                needs_review=True,
                items=[],
                error="LLM fallback could not parse valid JSON response.",
            )

        llm_doc_type = parsed_json.get("doc_type") or detected_doc_type
        company_name = parsed_json.get("company_name")
        tax_id = parsed_json.get("tax_id")
        grand_total = _safe_float(parsed_json.get("grand_total"))
        items = _normalize_items(parsed_json.get("items"))

        needs_review = not (company_name and grand_total is not None)
        if str(llm_doc_type) in {"statement_like", "unknown"}:
            needs_review = True

        return ParsedReceipt(
            filename=filename,
            success=True,
            doc_type=str(llm_doc_type),
            company_name=str(company_name).strip() if company_name else None,
            tax_id=str(tax_id).strip() if tax_id else None,
            grand_total=grand_total,
            raw_text=raw_text,
            needs_review=needs_review,
            items=items,
            error=None,
        )

    except Exception as exc:
        return ParsedReceipt(
            filename=filename,
            success=True,
            doc_type=detected_doc_type,
            raw_text=raw_text,
            needs_review=True,
            items=[],
            error=f"LLM fallback failed: {exc}",
        )