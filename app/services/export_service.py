import csv
import io

from sqlalchemy.orm import Session

from ..models import Receipt


def generate_receipts_csv(db: Session) -> io.StringIO:
    output = io.StringIO()
    writer = csv.writer(output)

    # header
    writer.writerow([
        "receipt_id",
        "filename",
        "company_name",
        "tax_id",
        "grand_total",
        "needs_review",
        "created_at",
        "item_id",
        "item_name",
        "qty",
        "unit_price",
        "line_total",
    ])

    receipts = db.query(Receipt).all()

    for receipt in receipts:
        if receipt.items:
            for item in receipt.items:
                writer.writerow([
                    receipt.id,
                    receipt.filename,
                    receipt.company_name,
                    receipt.tax_id,
                    receipt.grand_total,
                    receipt.needs_review,
                    receipt.created_at,
                    item.id,
                    item.item_name,
                    item.qty,
                    item.unit_price,
                    item.line_total,
                ])
        else:
            writer.writerow([
                receipt.id,
                receipt.filename,
                receipt.company_name,
                receipt.tax_id,
                receipt.grand_total,
                receipt.needs_review,
                receipt.created_at,
                "",
                "",
                "",
                "",
                "",
            ])

    output.seek(0)
    return output