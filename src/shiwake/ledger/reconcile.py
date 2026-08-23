"""領収書とカード明細行の突合（第1部 §6）。

★このシステムの心臓部。

同じ 1,234 円が「領収書」と「カード明細行」の両方に現れる。
これは同じ支出の別視点であって、2件の支出ではない。
ここを間違えると集計が全部壊れる。

一致条件（第1部 §6）:

  金額が完全に一致する   かつ
  日付差が 3日以内       かつ
  店名の類似度が 0.6 以上

★**候補が複数あるときは自動確定しない。** needs_review にして人間に投げる。
  勝手に選ぶと、間違ったリンクが「確定済み」として残る。

結果は links/YYYY-MM.json に永続化する。再実行しても壊れない
（既に確定したリンクを作り直さない）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .merchants import MerchantIndex

#: 第1部 §6 の一致条件
MAX_DATE_DIFF_DAYS = 3
MIN_NAME_SCORE = 0.6


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


@dataclass(frozen=True)
class CardLine:
    """カード明細の1行。"""

    statement_doc_id: str
    account: str
    line_id: str
    date: date
    description: str
    amount: int

    @property
    def key(self) -> str:
        """links に書く安定した識別子。"""
        return f"{self.statement_doc_id}:{self.line_id}"


@dataclass(frozen=True)
class Receipt:
    doc_id: str
    date: date
    issuer: str
    total: int
    payment_method: str | None
    #: デビットの引落元を決めるのに要る。クレジットでは使わない。
    card_last4: str | None = None
    #: コード決済・電子マネーの残高の名前（PayPay など）。
    account_hint: str | None = None


@dataclass(frozen=True)
class Candidate:
    receipt_doc_id: str
    card_line_key: str
    name_score: float
    date_diff: int

    def as_dict(self) -> dict:
        return {
            "doc_id": self.receipt_doc_id,
            "card_line": self.card_line_key,
            "name_score": round(self.name_score, 3),
            "date_diff": self.date_diff,
        }


@dataclass
class ReconcileResult:
    #: 候補が1つだけで、確定してよいもの
    confident: list[Candidate] = field(default_factory=list)
    #: 候補が複数あり、人が選ぶ必要があるもの
    ambiguous: dict[str, list[Candidate]] = field(default_factory=dict)
    #: 候補が見つからなかった領収書
    unmatched_receipts: list[str] = field(default_factory=list)
    #: 領収書が紐づかなかったカード明細行
    unmatched_card_lines: list[str] = field(default_factory=list)


def find_candidates(
    receipts: list[Receipt],
    card_lines: list[CardLine],
    merchants: MerchantIndex,
    already_linked: set[str] | None = None,
) -> ReconcileResult:
    """突合の候補を出す。**確定はしない。**"""
    already_linked = already_linked or set()
    result = ReconcileResult()

    open_receipts = [r for r in receipts if r.doc_id not in already_linked]
    open_lines = [line for line in card_lines if line.key not in already_linked]

    per_receipt: dict[str, list[Candidate]] = {}
    matched_lines: set[str] = set()

    for receipt in open_receipts:
        hits = [
            Candidate(
                receipt_doc_id=receipt.doc_id,
                card_line_key=line.key,
                name_score=score,
                date_diff=abs((line.date - receipt.date).days),
            )
            for line in open_lines
            if line.amount == receipt.total
            and abs((line.date - receipt.date).days) <= MAX_DATE_DIFF_DAYS
            and (score := merchants.match_score(receipt.issuer, line.description)) >= MIN_NAME_SCORE
        ]

        if not hits:
            result.unmatched_receipts.append(receipt.doc_id)
            continue
        per_receipt[receipt.doc_id] = sorted(hits, key=lambda c: (-c.name_score, c.date_diff))
        matched_lines.update(h.card_line_key for h in hits)

    # ★1つの明細行を複数の領収書が掴んだら、どれも確定しない。
    #   放っておくと同じ支出が2件の仕訳になる（＝二重計上）。
    #   どの領収書がその行かは機械には決められないので、人間に投げる。
    claimants: dict[str, set[str]] = {}
    for doc_id, hits in per_receipt.items():
        for hit in hits:
            claimants.setdefault(hit.card_line_key, set()).add(doc_id)
    contested = {key for key, docs in claimants.items() if len(docs) > 1}

    for doc_id, hits in per_receipt.items():
        if len(hits) == 1 and hits[0].card_line_key not in contested:
            result.confident.append(hits[0])
        else:
            result.ambiguous[doc_id] = hits

    result.unmatched_card_lines = [line.key for line in open_lines if line.key not in matched_lines]
    return result


# ── 永続化（links/YYYY-MM.json）──────────────────────────


@dataclass(frozen=True)
class Links:
    """確定した対応関係。再実行しても壊れない。"""

    month: str
    links: dict[str, str] = field(default_factory=dict)  # doc_id -> card_line_key

    def linked_keys(self) -> set[str]:
        return set(self.links) | set(self.links.values())

    def card_line_for(self, doc_id: str) -> str | None:
        return self.links.get(doc_id)

    def doc_for_card_line(self, key: str) -> str | None:
        return next((d for d, k in self.links.items() if k == key), None)


def load_links(path: Path) -> Links:
    month = path.stem
    if not path.is_file():
        return Links(month=month)
    data = json.loads(path.read_text(encoding="utf-8"))
    return Links(month=data.get("month", month), links=dict(data.get("links", {})))


def save_links(path: Path, links: Links, note: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"schema_version": 1, "month": links.month}
    if note:
        payload["_note"] = note
    payload["links"] = dict(sorted(links.links.items()))
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def confirm(links: Links, candidates: list[Candidate]) -> Links:
    """候補を確定してリンクに加える。既存のリンクは上書きしない。"""
    merged = dict(links.links)
    for c in candidates:
        merged.setdefault(c.receipt_doc_id, c.card_line_key)
    return Links(month=links.month, links=merged)
