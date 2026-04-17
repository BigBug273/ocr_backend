from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.export_service import generate_receipts_csv

router = APIRouter(tags=["export"])


@router.get("/receipts/export/csv")
def export_csv(db: Session = Depends(get_db)):
    csv_buffer = generate_receipts_csv(db)

    return StreamingResponse(
        iter([csv_buffer.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": "attachment; filename=receipts_export.csv"
        },
    )