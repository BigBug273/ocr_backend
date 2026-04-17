def detect_document_type(text: str, lines: list[str]) -> str:
    lowered = text.lower()

    # 1) บิลเงินสด / เขียนมือ
    if "cash sale" in lowered or "บิลเงินสด" in lowered:
        return "cash_bill_handwritten"

    # 2) เอกสารแนว statement / ใบเสร็จก่อนรับเงิน / เอกสารที่ไม่ใช่ receipt ปกติ
    # ทำให้เงื่อนไขแคบลง เพื่อไม่ให้ใบ full invoice ปกติหลุดมาโดน
    if (
        "ใบเสร็จก่อนรับเงิน" in lowered
        or (
            "ยอดคงค้าง" in lowered
            and "ยอดชำระ" in lowered
        )
        or (
            "ออกใบเสร็จภายหลัง" in lowered
            and ("ยอดคงค้าง" in lowered or "ยอดชำระ" in lowered)
        )
    ):
        return "statement_like"

    # 3) ใบกำกับเต็มรูป / invoice
    # ต้องเช็กก่อน short_receipt เพราะใบเต็มรูปอาจมีคำว่าใบเสร็จรับเงินและส่วนลดด้วย
    if (
        "inv" in lowered
        or "เครดิต" in lowered
        or ("description" in lowered and "unit price" in lowered and "amount" in lowered)
        or ("รายละเอียด" in lowered and "ราคาต่อหน่วย" in lowered and "มูลค่า" in lowered)
        or ("ใบกำกับภาษี/ใบเสร็จรับเงิน" in lowered and "เครดิต" in lowered)
        or ("รายละเอียด" in lowered and "จำนวน" in lowered and "มูลค่า" in lowered)
        or ("order no." in lowered and "qty" in lowered and "price" in lowered and "amount" in lowered)
    ):
        return "full_invoice"

    # 4) ใบเสร็จอย่างย่อ
    if (
        "vat included" in lowered
        or "ใบกำกับภาษีอย่างย่อ" in lowered
        or ("ใบเสร็จรับเงิน" in lowered and "ส่วนลด" in lowered)
        or ("grand total" in lowered and "discount" in lowered)
    ):
        return "short_receipt"

    return "unknown"