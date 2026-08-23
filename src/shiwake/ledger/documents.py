"""documents/*.json から突合用の型を組み立てる。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .reconcile import CardLine, Receipt


def _date(value: str):
    return datetime.fromisoformat(value).date()


def load_month(documents: Path, month: str) -> tuple[list[Receipt], list[CardLine]]:
    """指定した年月に関係する領収書とカード明細行を読む。

    領収書は発行日で、カード明細は対象期間で絞る。
    """
    receipts: list[Receipt] = []
    card_lines: list[CardLine] = []
    if not documents.is_dir():
        return receipts, card_lines

    for path in sorted(documents.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("type") == "receipt":
            issued = doc.get("issued_at")
            if not issued or not issued.startswith(month):
                continue
            receipts.append(
                Receipt(
                    doc_id=doc["doc_id"],
                    date=_date(issued),
                    issuer=(doc.get("issuer") or {}).get("name") or "",
                    total=doc.get("total") or 0,
                    payment_method=(doc.get("payment") or {}).get("method"),
                    card_last4=(doc.get("payment") or {}).get("card_last4"),
                )
            )
        elif doc.get("type") == "card_statement":
            period = doc.get("period") or {}
            if not str(period.get("from", "")).startswith(month):
                continue
            for t in doc.get("transactions", []):
                card_lines.append(
                    CardLine(
                        statement_doc_id=doc["doc_id"],
                        account=doc["account"],
                        line_id=t["line_id"],
                        date=_date(t["date"]),
                        description=t.get("raw_description") or "",
                        amount=t.get("amount") or 0,
                    )
                )
    return receipts, card_lines
