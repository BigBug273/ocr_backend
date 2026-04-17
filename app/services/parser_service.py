from ..schemas import OCRResult, ParsedReceipt
from .parsers.classifier import detect_document_type
from .parsers.common import prepare_lines
from .parsers.short_receipt_parser import parse_short_receipt
from .parsers.full_invoice_parser import parse_full_invoice
from .parsers.cash_bill_parser import parse_cash_bill


def parse_ocr_results(results: list[OCRResult]) -> list[ParsedReceipt]:
    parsed_results: list[ParsedReceipt] = []

    for result in results:
        text = (result.text or "").strip()

        if not result.success:
            parsed_results.append(
                ParsedReceipt(
                    filename=result.filename,
                    success=False,
                    raw_text=text,
                    needs_review=True,
                    error=result.error or "OCR failed",
                )
            )
            continue

        cleaned_text, lines = prepare_lines(text)
        doc_type = detect_document_type(cleaned_text, lines)

        if doc_type == "short_receipt":
            parsed = parse_short_receipt(result.filename, cleaned_text, lines)
        elif doc_type == "full_invoice":
            parsed = parse_full_invoice(result.filename, cleaned_text, lines)
        elif doc_type == "cash_bill_handwritten":
            parsed = parse_cash_bill(result.filename, cleaned_text, lines)
        else:
            parsed = parse_short_receipt(result.filename, cleaned_text, lines)
            parsed.needs_review = True

        parsed_results.append(parsed)

    return parsed_results