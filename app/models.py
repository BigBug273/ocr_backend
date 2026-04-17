from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    tax_id = Column(String(50), nullable=True)
    grand_total = Column(Float, nullable=True)
    raw_text = Column(Text, nullable=True)
    needs_review = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    items = relationship(
        "ReceiptItem",
        back_populates="receipt",
        cascade="all, delete-orphan"
    )


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=False)
    item_name = Column(String(255), nullable=True)
    qty = Column(Float, nullable=True)
    unit_price = Column(Float, nullable=True)
    line_total = Column(Float, nullable=True)

    receipt = relationship("Receipt", back_populates="items")