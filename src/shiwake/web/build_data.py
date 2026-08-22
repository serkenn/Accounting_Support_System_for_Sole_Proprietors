"""元帳 → Web 用の静的 JSON（第1部 §10）。

★画面に出る数字は全部ここで確定させる。
  ブラウザ側で集計し直さない。二重に実装するとズレるし、
  ズレたときにどちらが正しいか分からなくなる。

★「見込み」と「確定」を型で分ける（第3部 §4.2）。
  推定値を確定値と同じ形で渡すと、画面側で区別できなくなる。
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from shiwake.scopes import Scopes, matches

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LedgerPosting:
    """元帳から読んだ1 posting（web 用に必要な分だけ）。"""

    date: date
    payee: str
    narration: str
    account: str
    amount: int
    doc_id: str | None = None
    card_line: str | None = None
    pending: bool = False
    txn_id: str = ""


@dataclass
class WebData:
    files: dict[str, Any] = field(default_factory=dict)

    def write(self, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for name, payload in sorted(self.files.items()):
            path = out_dir / name
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
                encoding="utf-8",
            )
            written.append(path)
        return written


def _month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _is_expense(account: str) -> bool:
    return account.startswith("Expenses:")


def _is_income(account: str) -> bool:
    return account.startswith("Income:")


def _category_of(account: str) -> tuple[str, str]:
    """カテゴリ別集計の粒度と、その名前空間を返す。

        Expenses:Personal:Food:Groceries → ("personal", "Food")
        Expenses:Business:Supplies       → ("business", "Supplies")

    ★家計ビューには事業の費用も出る（実際に家計から出ていったお金なので）。
      名前空間を分けて返さないと、画面上で区別がつかなくなる。
    """
    parts = account.split(":")
    namespace = parts[1].lower() if len(parts) > 1 else "other"
    name = parts[2] if len(parts) > 2 else parts[-1]
    return namespace, name


def _by_transaction(postings: list[LedgerPosting]) -> dict[str, list[LedgerPosting]]:
    groups: dict[str, list[LedgerPosting]] = defaultdict(list)
    for p in postings:
        groups[p.txn_id].append(p)
    return groups


@dataclass(frozen=True)
class CashFlow:
    """1取引が家計の財布に与えた影響。"""

    month: str
    inflow: int
    outflow: int
    #: 出ていった額を、何に使ったかで割り振ったもの
    by_category: dict[tuple[str, str], int]


def _household_cash_flow(group: list[LedgerPosting], scopes: Scopes) -> CashFlow | None:
    """家計の財布の増減から、その取引の出入りを出す。

    ★「いくら出たか」を決めるのは貸方（どの財布から出たか）。
      借方（何に使ったか）で数えると、事業用口座を分けた瞬間に
      家計の支出が過大になる（事業の口座で払った分まで乗る）。

    カテゴリの内訳は借方から取る。「何に使ったか」はそちらにあるため。
    出た額を、費用の posting に按分して割り当てる。
    """
    # ★期首残高や元入金は「入ってきたお金」ではない。
    #   最初から持っていたものを宣言しているだけなので、出入りから外す。
    #   ここを数えると、初月の収入が期首残高の分だけ跳ね上がる。
    if any(p.account.startswith("Equity:Opening-Balances") for p in group):
        return None

    delta = sum(p.amount for p in group if scopes.is_wallet(p.account))
    if delta == 0:
        # 財布どうしの振替（カードの引落など）。出入りではない
        return None

    month = _month_of(group[0].date)
    if delta > 0:
        return CashFlow(month=month, inflow=delta, outflow=0, by_category={})

    outflow = -delta
    expenses = [p for p in group if _is_expense(p.account) and p.amount > 0]
    total = sum(p.amount for p in expenses)

    by_category: dict[tuple[str, str], int] = defaultdict(int)
    if total > 0:
        assigned = 0
        for i, p in enumerate(expenses):
            # 端数は最後の1件に寄せる。合計が outflow と必ず一致するように
            share = outflow - assigned if i == len(expenses) - 1 else outflow * p.amount // total
            by_category[_category_of(p.account)] += share
            assigned += share
    else:
        # 費用の posting が無い出金（貸付・振替など）
        by_category[("other", "その他")] += outflow

    return CashFlow(month=month, inflow=0, outflow=outflow, by_category=dict(by_category))


def build_monthly_summary(postings: list[LedgerPosting], scope: str, scopes: Scopes) -> list[dict]:
    """月次の収入・支出・差引（第1部 §10-1）。

    家計は**財布の出入り**（第5部 §9.1「いくら入っていくら出たか」）、
    事業は**発生ベース**（決算書と同じ範囲）で数える。数え方が違う。
    """
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"income": 0, "expense": 0, "business_share": 0}
    )

    if scope == "household" and scopes.has_wallets:
        for group in _by_transaction(postings).values():
            flow = _household_cash_flow(group, scopes)
            if flow is None:
                continue
            bucket = buckets[flow.month]
            bucket["income"] += flow.inflow
            bucket["expense"] += flow.outflow
            # ★このうち事業のために出た分。同額が事業への持分に変わっている
            bucket["business_share"] += sum(
                amount
                for (namespace, _), amount in flow.by_category.items()
                if namespace == "business"
            )
    else:
        for p in postings:
            if not scopes.in_scope(scope, p.account):
                continue
            month = _month_of(p.date)
            if _is_expense(p.account):
                buckets[month]["expense"] += p.amount
            elif _is_income(p.account):
                buckets[month]["income"] += -p.amount

    return [
        {
            "month": month,
            "income": v["income"],
            "expense": v["expense"],
            "net": v["income"] - v["expense"],
            "business_share": v["business_share"],
        }
        for month, v in sorted(buckets.items())
    ]


def build_categories(
    postings: list[LedgerPosting], month: str, scope: str, scopes: Scopes
) -> list[dict]:
    """カテゴリ別の支出（第3部 §8.1）。

    家計は財布から出た額を、何に使ったかで割り振る。
    事業は発生ベースでそのまま集計する。
    """
    totals: dict[tuple[str, str], int] = defaultdict(int)

    if scope == "household" and scopes.has_wallets:
        for group in _by_transaction(postings).values():
            flow = _household_cash_flow(group, scopes)
            if flow is None or flow.month != month:
                continue
            for key, amount in flow.by_category.items():
                totals[key] += amount
    else:
        for p in postings:
            if not _is_expense(p.account) or not scopes.in_scope(scope, p.account):
                continue
            if _month_of(p.date) != month:
                continue
            totals[_category_of(p.account)] += p.amount

    grand = sum(totals.values())
    return [
        {
            "namespace": namespace,
            "category": name,
            "amount": amount,
            "ratio": round(amount / grand, 4) if grand else 0.0,
        }
        for (namespace, name), amount in sorted(totals.items(), key=lambda kv: -kv[1])
    ]


def build_transactions(postings: list[LedgerPosting], scope: str, scopes: Scopes) -> list[dict]:
    """明細一覧（第1部 §10-3）。1取引1行にまとめる。"""
    by_txn: dict[str, list[LedgerPosting]] = defaultdict(list)
    for p in postings:
        by_txn[p.txn_id].append(p)

    rows = []
    for txn_id, group in by_txn.items():
        legs = [p for p in group if _is_expense(p.account) or _is_income(p.account)]
        if not legs:
            continue
        primary = max(legs, key=lambda p: abs(p.amount))
        if not scopes.in_scope(scope, primary.account):
            continue
        rows.append(
            {
                "id": txn_id,
                "date": primary.date.isoformat(),
                "payee": primary.payee,
                "narration": primary.narration,
                "account": primary.account,
                "amount": primary.amount,
                "doc_id": primary.doc_id,
                "card_line": primary.card_line,
                "pending": primary.pending,
                "postings": [
                    {"account": p.account, "amount": p.amount}
                    for p in sorted(group, key=lambda x: x.account)
                ],
            }
        )
    return sorted(rows, key=lambda r: (r["date"], r["payee"]))


def build_accounts(postings: list[LedgerPosting], scope: str, scopes: Scopes) -> list[dict]:
    """資産・負債の残高（第1部 §10-5）。"""
    balances: dict[str, int] = defaultdict(int)
    for p in postings:
        if not scopes.in_scope(scope, p.account):
            continue
        if p.account.startswith(("Assets:", "Liabilities:")):
            balances[p.account] += p.amount
    return [
        {"account": account, "balance": balance}
        for account, balance in sorted(balances.items())
        if balance != 0
    ]


def build_attention(postings: list[LedgerPosting], documents: list[dict]) -> dict:
    """対応が必要なもの（第3部 §8.1）。

    ★ここに出ないものは、忘れられる。
    """
    needs_review = [d["doc_id"] for d in documents if d.get("needs_review")]
    pending = sorted({p.txn_id for p in postings if p.pending})
    unlinked = [
        d["doc_id"]
        for d in documents
        if d.get("type") == "receipt" and d.get("payment", {}).get("method") == "credit_card"
    ]
    return {
        "needs_review": {"count": len(needs_review), "doc_ids": sorted(needs_review)},
        "pending": {"count": len(pending), "transaction_ids": pending},
        "receipts_awaiting_statement": {"count": len(unlinked)},
    }


def build_web_data(
    postings: list[LedgerPosting],
    documents: list[dict],
    scopes: Scopes,
    generated_at: str,
    commit: str = "",
    months: list[str] | None = None,
    note: str | None = None,
) -> WebData:
    """静的 JSON 一式を組み立てる。"""
    known_months = months or sorted({_month_of(p.date) for p in postings})

    # ★既定で開く月は「最後の月」ではなく「取引が一番多い直近の月」。
    #   月初に1件だけ入った翌月を開くと、実質空の画面が出て
    #   「壊れている」ように見える。
    counts: dict[str, int] = defaultdict(int)
    for p in postings:
        if _is_expense(p.account) or _is_income(p.account):
            counts[_month_of(p.date)] += 1
    substantial = [m for m in known_months if counts[m] >= 3]
    latest = (substantial or known_months or [""])[-1]

    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        # ★紙に刷ったときにリポジトリの状態と紐づけるため（第3部 §10）
        "commit": commit,
        "months": known_months,
        "latest_month": latest,
        "scopes": {name: {"label": scopes.label(name)} for name in ("household", "business")},
    }

    files: dict[str, Any] = {"meta.json": meta}

    for scope in ("household", "business"):
        files[f"summary-{scope}.json"] = {
            "scope": scope,
            "monthly": build_monthly_summary(postings, scope, scopes),
        }
        files[f"categories-{scope}.json"] = {
            "scope": scope,
            "months": {m: build_categories(postings, m, scope, scopes) for m in known_months},
        }
        files[f"transactions-{scope}.json"] = {
            "scope": scope,
            "transactions": build_transactions(postings, scope, scopes),
        }
        files[f"accounts-{scope}.json"] = {
            "scope": scope,
            "accounts": build_accounts(postings, scope, scopes),
        }

    files["attention.json"] = build_attention(postings, documents)
    files["documents.json"] = {
        "documents": [
            {
                "doc_id": d.get("doc_id"),
                "type": d.get("type"),
                "origin": d.get("origin"),
                "needs_review": d.get("needs_review", False),
                "review_reason": d.get("review_reason"),
                "issuer": (d.get("issuer") or {}).get("name"),
                "issued_at": d.get("issued_at"),
                "total": d.get("total"),
                "tax_breakdown": d.get("tax_breakdown"),
                "original_ref": (d.get("source") or {}).get("original_ref"),
                "original_ext": (d.get("source") or {}).get("original_ext"),
                "page_count": d.get("page_count", 1),
                "derivative_error": d.get("derivative_error"),
            }
            for d in sorted(documents, key=lambda x: x.get("doc_id") or "")
        ]
    }

    if note:
        # 合成データから作った出力であることを、全ファイルに残す（第13部 §6.2）
        for payload in files.values():
            if isinstance(payload, dict):
                payload["_note"] = note

    return WebData(files=files)


def matches_any(patterns: list[str], account: str) -> bool:
    return any(matches(p, account) for p in patterns)
