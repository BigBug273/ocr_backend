from typing import List

from fastapi import APIRouter, File, UploadFile

from ..schemas import OCRResponse, OCRResult
from ..services.ocr_service import extract_text_from_file, validate_filename

router = APIRouter(prefix="/ocr", tags=["ocr"])


@router.post("", response_model=OCRResponse)
async def run_ocr(files: List[UploadFile] = File(...)):
    results: list[OCRResult] = []

    for file in files:
        filename = file.filename or "uploaded_file"

        if not validate_filename(filename):
            results.append(
                OCRResult(
                    filename=filename,
                    success=False,
                    text="",
                    error="Unsupported file type. Allowed: .jpg, .jpeg, .png, .pdf, .txt",
                )
            )
            continue

        try:
            content = await file.read()
            text = extract_text_from_file(filename, content)
            results.append(OCRResult(filename=filename, success=True, text=text, error=None))
        except Exception as exc:
            results.append(OCRResult(filename=filename, success=False, text="", error="OCR processing failed"))

    return OCRResponse(results=results)
