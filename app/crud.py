from sqlalchemy.orm import Session

from . import models, schemas



def _build_receipt_model(payload: schemas.ParsedReceipt) -> models.Receipt:
    receipt = models.Receipt(
        filename=payload.filename,
        company_name=payload.company_name,
        tax_id=payload.tax_id,
        grand_total=payload.grand_total,
        raw_text=payload.raw_text,
        needs_review=1 if payload.needs_review else 0,
    )

    for item in payload.items:
        receipt.items.append(
            models.ReceiptItem(
                item_name=item.item_name,
                qty=item.qty,
                unit_price=item.unit_price,
                line_total=item.line_total,
            )
        )

    return receipt



def create_many_receipts(
    db: Session,
    payloads: list[schemas.ParsedReceipt],
) -> list[models.Receipt]:
    valid_payloads = [payload for payload in payloads if payload.success and payload.raw_text]
    if not valid_payloads:
        return []

    receipts = [_build_receipt_model(payload) for payload in valid_payloads]
    db.add_all(receipts)
    db.commit()

    for receipt in receipts:
        db.refresh(receipt)

    return receipts



def get_receipts(db: Session) -> list[models.Receipt]:
    return db.query(models.Receipt).order_by(models.Receipt.id.desc()).all()



def get_receipt_by_id(db: Session, receipt_id: int):
    return db.query(models.Receipt).filter(models.Receipt.id == receipt_id).first()
