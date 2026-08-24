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

    領収書は発行日で、カード明細行は利用日で絞る（どちらも暦月）。
    3つめは doc_id → 費用科目（領収書の側で指定されたもの）。
    """
    receipts: list[Receipt] = []
    card_lines: list[CardLine] = []
    receipt_accounts: dict[str, str] = {}
    skipped: list[str] = []
    if not documents.is_dir():
        return receipts, card_lines, receipt_accounts

    for path in sorted(documents.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("type") == "receipt":
            issued = doc.get("issued_at")
            if not issued or not issued.startswith(month):
                continue
            if doc.get("total") is None:
                # ★読めなかった金額を 0 として入れない。貸借は合うので
                #   検算も通り、費用が黙って過小になる。
                skipped.append(doc["doc_id"])
                continue
            receipts.append(
                Receipt(
                    doc_id=doc["doc_id"],
                    date=_date(issued),
                    issuer=(doc.get("issuer") or {}).get("name") or "",
                    total=doc["total"],
                    payment_method=(doc.get("payment") or {}).get("method"),
                    card_last4=(doc.get("payment") or {}).get("card_last4"),
                    account_hint=(doc.get("payment") or {}).get("account_hint"),
                )
            )
            account = _receipt_account(doc)
            if account:
                receipt_accounts[doc["doc_id"]] = account
        elif doc.get("type") == "card_statement":
            for t in doc.get("transactions", []):
                # ★明細行は「その行の利用日」で月に分ける。締め期間で分けない。
                #   締め期間は暦月をまたぐ（例 4/16〜5/15）ので、期間で分けると
                #   5/15 の明細行が 2026-04 に、その領収書が 2026-05 に落ちる。
                #   別の月に落ちた両者は突合の候補にすら上がらず、
                #   **同じ支出が領収書と明細行の2件として元帳に入る。**
                if not str(t.get("date", "")).startswith(month):
                    continue
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


def load_skipped(documents: Path, month: str) -> list[str]:
    """金額が読めず、元帳に入れなかった領収書の doc_id。

    ★黙って消すと、抜けていることに誰も気づかない。
    """
    out: list[str] = []
    if not documents.is_dir():
        return out
    for path in sorted(documents.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("type") != "receipt" or doc.get("total") is not None:
            continue
        issued = doc.get("issued_at")
        if issued and issued.startswith(month):
            out.append(doc["doc_id"])
    return out
