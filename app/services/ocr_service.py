import os
import tempfile
from pathlib import Path
from typing import Optional

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".txt"}
OCR_PROVIDER = "typhoon-ocr"


def validate_filename(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS


def is_ocr_configured() -> bool:
    return bool(os.getenv("TYPHOON_OCR_API_KEY"))


def get_ocr_provider() -> str:
    return OCR_PROVIDER


def _decode_text_bytes(content: bytes) -> str:
    try:
        return content.decode("utf-8").strip()
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="ignore").strip()


def _run_typhoon_ocr(temp_path: str, ext: str) -> str:
    try:
        from typhoon_ocr import ocr_document
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Typhoon OCR package is not installed. Run: pip install typhoon-ocr"
        ) from exc

    api_key = os.getenv("TYPHOON_OCR_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing TYPHOON_OCR_API_KEY in environment. Add it to .env before scanning images/PDFs."
        )

    # Official docs indicate the helper reads the API key from TYPHOON_OCR_API_KEY.
    # For PDFs, page_num defaults to 1 and images always use page 1 behavior.
    markdown = ocr_document(pdf_or_image_path=temp_path)
    if not markdown:
        raise RuntimeError("Typhoon OCR returned empty text")
    return str(markdown).strip()


def extract_text_from_file(filename: str, content: bytes) -> str:
    ext = Path(filename).suffix.lower()

    if ext == ".txt":
        return _decode_text_bytes(content)

    if ext not in {".jpg", ".jpeg", ".png", ".pdf"}:
        raise RuntimeError(f"Unsupported file type: {ext}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
        temp_file.write(content)
        temp_path = temp_file.name

    try:
        return _run_typhoon_ocr(temp_path, ext)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
