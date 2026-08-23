"""documents/*.json から突合用の型を組み立てる。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .reconcile import CardLine, Receipt


def _date(value: str):
    return datetime.fromisoformat(value).date()


def _receipt_account(doc: dict) -> str | None:
    """領収書の側で指定された費用科目。

    ★店名だけで分類が決まらない店（雑貨店、運送、タクシーなど）は、
      categories.yaml に書かず、領収書ごとに科目を指定する。
      指定が読まれないと、私用と事業が混ざったまま黙って通る。
    """
    accounts = {line.get("account") for line in doc.get("lines") or [] if line.get("account")}
    if not accounts:
        return None
    if len(accounts) > 1:
        # ★片方に寄せない。寄せた側が丸ごと間違う。
        raise ValueError(
            f"{doc.get('doc_id')}: 1枚の領収書に複数の科目が指定されています"
            f"（{', '.join(sorted(accounts))}）。"
            "明細ごとの分割にはまだ対応していないので、"
            "領収書を分けるか、科目を1つにしてください"
        )
    return accounts.pop()


def load_month(documents: Path, month: str) -> tuple[list[Receipt], list[CardLine], dict[str, str]]:
    """指定した年月に関係する領収書とカード明細行を読む。

    領収書は発行日で、カード明細は対象期間で絞る。
    3つめは doc_id → 費用科目（領収書の側で指定されたもの）。
    """
    receipts: list[Receipt] = []
    card_lines: list[CardLine] = []
    receipt_accounts: dict[str, str] = {}
    if not documents.is_dir():
        return receipts, card_lines, receipt_accounts

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
                    account_hint=(doc.get("payment") or {}).get("account_hint"),
                )
            )
            account = _receipt_account(doc)
            if account:
                receipt_accounts[doc["doc_id"]] = account
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
    return receipts, card_lines, receipt_accounts
