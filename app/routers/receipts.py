from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..schemas import (
    OCRResult,
    ParseReceiptsRequest,
    ParseReceiptsResponse,
    ReceiptRead,
    SaveReceiptsRequest,
    ScanReceiptsResponse,
)
from ..services.agentic_parser_service import agentic_parse_ocr_results
from ..services.ocr_service import extract_text_from_file, validate_filename
from ..services.parser_service import parse_ocr_results

router = APIRouter(tags=["receipts"])


@router.post("/receipts/scan", response_model=ScanReceiptsResponse)
async def scan_receipts(
    files: Annotated[list[UploadFile], File(..., description="Upload receipt files")]
):
    ocr_results: list[OCRResult] = []

    for file in files:
        filename = file.filename or "uploaded_file"

        if not validate_filename(filename):
            ocr_results.append(
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
            ocr_results.append(
                OCRResult(
                    filename=filename,
                    success=True,
                    text=text,
                    error=None,
                )
            )
        except Exception as exc:
            ocr_results.append(
                OCRResult(
                    filename=filename,
                    success=False,
                    text="",
                    error=str(exc),
                )
            )

    parsed_results = agentic_parse_ocr_results(ocr_results)
    return ScanReceiptsResponse(results=parsed_results)


@router.post("/parse-receipts", response_model=ParseReceiptsResponse)
def parse_receipts(payload: ParseReceiptsRequest):
    # route นี้เก็บไว้เผื่อ parse OCRResult ที่มีอยู่แล้ว
    parsed_results = parse_ocr_results(payload.results)
    return ParseReceiptsResponse(results=parsed_results)


@router.post("/save-receipts", response_model=list[ReceiptRead])
def save_receipts(payload: SaveReceiptsRequest, db: Session = Depends(get_db)):
    saved = crud.create_many_receipts(db, payload.results)
    if not saved:
        raise HTTPException(status_code=400, detail="No valid parsed receipts to save")
    return saved


@router.get("/receipts", response_model=list[ReceiptRead])
def list_receipts(db: Session = Depends(get_db)):
    return crud.get_receipts(db)


@router.get("/receipts/{receipt_id}", response_model=ReceiptRead)
def get_receipt(receipt_id: int, db: Session = Depends(get_db)):
    receipt = crud.get_receipt_by_id(db, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt