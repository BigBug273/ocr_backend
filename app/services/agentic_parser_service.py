from ..schemas import OCRResult, ParsedReceipt
from .parsers.classifier import detect_document_type
from .parsers.common import prepare_lines
from .parsers.short_receipt_parser import parse_short_receipt
from .parsers.full_invoice_parser import parse_full_invoice
from .parsers.cash_bill_parser import parse_cash_bill
from .parsers.llm_fallback_parser import parse_with_llm_fallback


def _score_parsed_result(parsed: ParsedReceipt) -> int:
    score = 0

    if parsed.company_name:
        score += 2
    if parsed.tax_id:
        score += 1
    if parsed.grand_total is not None:
        score += 3
    if parsed.items:
        score += 3
    if not parsed.needs_review:
        score += 1

    return score


def _set_doc_type(parsed: ParsedReceipt, doc_type: str) -> ParsedReceipt:
    parsed.doc_type = doc_type
    return parsed


def _mark_for_review(parsed: ParsedReceipt, reason: str | None = None) -> ParsedReceipt:
    parsed.needs_review = True
    if reason and not parsed.error:
        parsed.error = reason
    return parsed


def _looks_like_non_receipt_document(cleaned_text: str) -> bool:
    lowered = cleaned_text.lower()

    non_receipt_signals = [
        "ใบเสร็จก่อนรับเงิน",
        "ยอดคงค้าง",
        "ยอดชำระ",
        "ออกใบเสร็จภายหลัง",
        "ตรวจสอบโดย",
        "ผู้รับเงิน",
        "ยอดค้าง",
        "หมายเหตุ",
    ]

    hit_count = sum(1 for signal in non_receipt_signals if signal in lowered)
    return hit_count >= 2


def _item_name_looks_suspicious(item_name: str) -> bool:
    lowered = (item_name or "").lower().strip()

    suspicious_keywords = [
        "แขวง",
        "เขต",
        "จังหวัด",
        "ถนน",
        "ซอย",
        "โทร",
        "โทรสาร",
        "เลขที่",
        "ยอดคงค้าง",
        "ยอดชำระ",
        "ตรวจสอบโดย",
        "ผู้รับเงิน",
        "หมายเหตุ",
    ]

    return any(keyword in lowered for keyword in suspicious_keywords)


def _parsed_result_needs_extra_review(parsed: ParsedReceipt, detected_doc_type: str) -> bool:
    if detected_doc_type in {"unknown", "statement_like"}:
        return True

    if not parsed.company_name or parsed.grand_total is None:
        return True

    if parsed.items:
        suspicious_count = sum(
            1 for item in parsed.items if _item_name_looks_suspicious(item.item_name)
        )
        if suspicious_count >= 1:
            return True

    return False


def _should_try_llm_fallback(
    parsed: ParsedReceipt,
    detected_doc_type: str,
    forced_review_mode: bool,
) -> bool:
    # เรียก LLM เฉพาะเคสที่ยากจริง เพื่อลด quota และลดความแกว่ง
    if detected_doc_type in {"unknown", "statement_like", "cash_bill_handwritten"}:
        return True

    if forced_review_mode:
        return True

    # ถ้าเป็น full_invoice หรือ short_receipt แล้ว parse ได้อยู่ อย่าเพิ่งยิง LLM
    if detected_doc_type in {"full_invoice", "short_receipt"}:
        if parsed.company_name and parsed.grand_total is not None and parsed.items:
            return False

    # ค่อยลอง LLM เมื่อข้อมูลสำคัญหายจริง
    if parsed.grand_total is None:
        return True

    if not parsed.company_name:
        return True

    if not parsed.items:
        return True

    # ถ้าคะแนนต่ำมาก ค่อยลอง
    if _score_parsed_result(parsed) < 5:
        return True

    return False


def _choose_better_result(rule_based: ParsedReceipt, llm_based: ParsedReceipt) -> ParsedReceipt:
    # ถ้า LLM ล้มเหลวจริง ค่อยใช้ของเดิม
    if llm_based.error and not llm_based.items and llm_based.grand_total is None:
        return rule_based

    # ถ้า rule-based ยังข้อมูลไม่ครบ ให้ใช้ LLM ทันที
    if rule_based.grand_total is None or not rule_based.items:
        return llm_based

    # ถ้า LLM ได้ข้อมูลมากกว่า ให้ใช้ LLM
    rule_score = _score_parsed_result(rule_based)
    llm_score = _score_parsed_result(llm_based)

    if llm_score > rule_score:
        return llm_based

    return rule_based


def _run_parser_by_type(filename: str, cleaned_text: str, lines: list[str], doc_type: str) -> ParsedReceipt:
    if doc_type == "short_receipt":
        parsed = parse_short_receipt(filename, cleaned_text, lines)
    elif doc_type == "full_invoice":
        parsed = parse_full_invoice(filename, cleaned_text, lines)
    elif doc_type == "cash_bill_handwritten":
        parsed = parse_cash_bill(filename, cleaned_text, lines)
    elif doc_type == "statement_like":
        parsed = parse_full_invoice(filename, cleaned_text, lines)
        parsed.needs_review = True
    else:
        parsed = parse_short_receipt(filename, cleaned_text, lines)
        parsed.needs_review = True

    return _set_doc_type(parsed, doc_type)


def agentic_parse_ocr_results(results: list[OCRResult]) -> list[ParsedReceipt]:
    parsed_results: list[ParsedReceipt] = []

    for result in results:
        text = (result.text or "").strip()

        if not result.success:
            parsed_results.append(
                ParsedReceipt(
                    filename=result.filename,
                    success=False,
                    doc_type="unknown",
                    raw_text=text,
                    needs_review=True,
                    items=[],
                    error=result.error or "OCR failed",
                )
            )
            continue

        cleaned_text, lines = prepare_lines(text)
        detected_doc_type = detect_document_type(cleaned_text, lines)
        forced_review_mode = _looks_like_non_receipt_document(cleaned_text)

        # 1) parser หลักตาม classifier
        primary = _run_parser_by_type(result.filename, cleaned_text, lines, detected_doc_type)

        # 2) fallback แบบ rule-based เพิ่มเติม
        fallback_candidates: list[ParsedReceipt] = [primary]
        tried_types = {detected_doc_type}

        if detected_doc_type != "statement_like":
            if "full_invoice" not in tried_types:
                fallback_candidates.append(
                    _run_parser_by_type(result.filename, cleaned_text, lines, "full_invoice")
                )
                tried_types.add("full_invoice")

            if "short_receipt" not in tried_types:
                fallback_candidates.append(
                    _run_parser_by_type(result.filename, cleaned_text, lines, "short_receipt")
                )
                tried_types.add("short_receipt")

            lowered = cleaned_text.lower()
            if "cash sale" in lowered or "บิลเงินสด" in lowered:
                if "cash_bill_handwritten" not in tried_types:
                    fallback_candidates.append(
                        _run_parser_by_type(
                            result.filename,
                            cleaned_text,
                            lines,
                            "cash_bill_handwritten",
                        )
                    )
                    tried_types.add("cash_bill_handwritten")

        best = max(fallback_candidates, key=_score_parsed_result)

        # 3) ค่อยลอง LLM fallback เฉพาะตอนจำเป็นจริง
        if _should_try_llm_fallback(best, detected_doc_type, forced_review_mode):
            llm_result = parse_with_llm_fallback(
                filename=result.filename,
                raw_text=cleaned_text,
                detected_doc_type=detected_doc_type,
            )
            best = _choose_better_result(best, llm_result)

        # 4) apply review policy
        if forced_review_mode or detected_doc_type in {"unknown", "statement_like"}:
            best.needs_review = True
            if not best.error:
                best.error = "Document may require manual review."

        if _score_parsed_result(best) < 6:
            best = _mark_for_review(best, "Please review manually.")

        if _parsed_result_needs_extra_review(best, detected_doc_type):
            best = _mark_for_review(best, "Please review manually.")

        if not best.doc_type:
            best.doc_type = detected_doc_type

        parsed_results.append(best)

    return parsed_results