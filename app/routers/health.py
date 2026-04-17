from fastapi import APIRouter

from ..schemas import HealthResponse
from ..services.ocr_service import get_ocr_provider, is_ocr_configured

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        service="Receipt OCR Backend",
        version="1.0.0",
        ocr_configured=is_ocr_configured(),
        ocr_provider=get_ocr_provider(),
    )
