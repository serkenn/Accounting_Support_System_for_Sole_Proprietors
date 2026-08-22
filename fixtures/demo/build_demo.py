"""SYNTHETIC — 合成の1か月分から元帳を組み立てるデモ（第13部 §11）。

実データは一切含みません。ここに実在の店名・金額を書かないこと。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from shiwake.ledger.build import build_month, card_debit_transaction
from shiwake.ledger.categorize import load_categories
from shiwake.ledger.merchants import load_merchants
from shiwake.ledger.reconcile import (
    Candidate,
    CardLine,
    Links,
    Receipt,
    confirm,
    find_candidates,
    save_links,
)

BASE = Path(__file__).parent
HEADER = (
    ";; SYNTHETIC — 合成データから生成した元帳です。実在の取引ではありません。\n"
    ";; このファイルは生成物です。手で編集しません。"
)


def load() -> tuple[dict, list[Receipt], list[CardLine]]:
    docs = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((BASE / "documents").glob("*.json"))
    ]
    stmt = next(d for d in docs if d["type"] == "card_statement")
    lines = [
        CardLine(
            stmt["doc_id"],
            stmt["account"],
            t["line_id"],
            datetime.fromisoformat(t["date"]).date(),
            t["raw_description"],
            t["amount"],
        )
        for t in stmt["transactions"]
    ]
    receipts = [
        Receipt(
            d["doc_id"],
            datetime.fromisoformat(d["issued_at"]).date(),
            d["issuer"]["name"],
            d["total"],
            d["payment"]["method"],
        )
        for d in docs
        if d["type"] == "receipt"
    ]
    return stmt, receipts, lines


def main() -> None:
    stmt, receipts, lines = load()
    merchants = load_merchants(BASE / "rules" / "merchants.yaml")
    categorizer = load_categories(BASE / "rules" / "categories.yaml", merchants)

    found = find_candidates(receipts, lines, merchants)
    links = confirm(Links(month="2026-07"), found.confident)
    # 曖昧だった1件を「人が選んだ」ものとして確定する（自動では確定しない）
    links = confirm(
        links, [Candidate("doc_2026-07-14_sample_002715", f"{stmt['doc_id']}:L005", 1.0, 0)]
    )
    save_links(
        BASE / "links" / "2026-07.json",
        links,
        note="SYNTHETIC — 合成データです。実在の取引ではありません。",
    )

    result = build_month(
        receipts,
        lines,
        links,
        categorizer,
        receipt_accounts={"doc_2026-08-02_sample_00271a:credit": stmt["account"]},
    )
    result.transactions.append(
        card_debit_transaction(
            date(2026, 8, 27),
            "サンプルカード 7月分引落",
            stmt["account"],
            "Assets:Personal:Bank:Sample",
            stmt["statement_total"],
            meta={"statement": stmt["doc_id"]},
        )
    )

    out = BASE / "ledger"
    out.mkdir(exist_ok=True)
    (out / "2026-07.beancount").write_text(result.render(HEADER), encoding="utf-8")

    for issue in result.issues:
        print(issue.format())
    print(f"仕訳 {len(result.transactions)} 件 / 曖昧 {len(found.ambiguous)} 件")


if __name__ == "__main__":
    main()
