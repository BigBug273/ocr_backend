from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    ocr_configured: bool
    ocr_provider: str


class ReceiptItemBase(BaseModel):
    item_name: str
    qty: Optional[float] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None


class ReceiptItemCreate(ReceiptItemBase):
    pass


class ReceiptItemRead(ReceiptItemBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class OCRResult(BaseModel):
    filename: str
    success: bool
    text: str = ""
    error: Optional[str] = None


class OCRResponse(BaseModel):
    results: List[OCRResult]


class ParsedReceipt(BaseModel):
    filename: str
    success: bool
    doc_type: Optional[str] = None
    company_name: Optional[str] = None
    tax_id: Optional[str] = None
    grand_total: Optional[float] = None
    raw_text: str = ""
    needs_review: bool = True
    items: List[ReceiptItemCreate] = []
    error: Optional[str] = None


class ParseReceiptsRequest(BaseModel):
    results: List[OCRResult]


class ParseReceiptsResponse(BaseModel):
    results: List[ParsedReceipt]


class ScanReceiptsResponse(BaseModel):
    results: List[ParsedReceipt]


class SaveReceiptsRequest(BaseModel):
    results: List[ParsedReceipt]


class ReceiptRead(BaseModel):
    id: int
    filename: str
    company_name: Optional[str] = None
    tax_id: Optional[str] = None
    grand_total: Optional[float] = None
    raw_text: str = ""
    needs_review: bool = True
    created_at: datetime
    items: List[ReceiptItemRead] = []

    model_config = ConfigDict(from_attributes=True)