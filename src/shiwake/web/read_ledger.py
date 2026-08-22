"""元帳から Web 用の posting を読む。

★beancount / beanquery は import しない（D57）。
  bean-query を CSV で呼び、結果だけを受け取る。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from shiwake.ledger.query import run_query

from .build_data import LedgerPosting

#: ★メタの参照は any_meta()。meta() は存在しない関数だが、
#:   beanquery はエラーにせず空を返すので、間違えると黙って全部 null になる。
QUERY = (
    "SELECT id, date, payee, narration, account, number, currency, "
    "any_meta('doc_id') AS doc_id, "
    "any_meta('card_line') AS card_line, "
    "any_meta('pending') AS pending"
)


def _int(raw: str | None) -> int:
    text = (raw or "0").strip()
    if not text:
        return 0
    return int(float(text))


def load_ledger_postings(main_file: Path) -> list[LedgerPosting]:
    rows = run_query(main_file, QUERY)
    postings: list[LedgerPosting] = []
    for row in rows:
        if (row.get("currency") or "JPY") not in ("JPY", ""):
            continue
        postings.append(
            LedgerPosting(
                date=datetime.fromisoformat(row["date"]).date(),
                payee=(row.get("payee") or "").strip(),
                narration=(row.get("narration") or "").strip(),
                account=row["account"],
                amount=_int(row.get("number")),
                doc_id=(row.get("doc_id") or "").strip() or None,
                card_line=(row.get("card_line") or "").strip() or None,
                pending=(row.get("pending") or "").strip().upper() in ("TRUE", "T", "1"),
                txn_id=row.get("id") or "",
            )
        )
    return postings
