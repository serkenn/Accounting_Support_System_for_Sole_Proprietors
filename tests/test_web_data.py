"""Web 用の静的データ（第1部 §10 / 第3部）。

★画面に出る数字はここで確定する。ブラウザ側で集計し直さない。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from shiwake.scopes import load_scopes
from shiwake.web import LedgerPosting, build_web_data

RULES = Path(__file__).resolve().parents[2] / "ledger-data" / "rules" / "scopes.yaml"


@pytest.fixture
def scopes():
    return load_scopes(RULES)


def p(account, amount, d=(2026, 7, 14), payee="サンプルストア", txn="t1", **kw):
    return LedgerPosting(
        date=date(*d), payee=payee, narration="", account=account, amount=amount, txn_id=txn, **kw
    )


def build(postings, scopes, documents=None):
    return build_web_data(
        postings=postings,
        documents=documents or [],
        scopes=scopes,
        generated_at="2026-08-22T22:00:00+09:00",
        commit="abc1234",
    ).files


# ── 所得区分の分離が画面まで通っていること ──────────────


def test_salary_never_reaches_the_business_view(scopes):
    postings = [
        p("Income:Employment:Sample", -120000),
        p("Assets:Personal:Bank:Sample", 120000),
    ]
    files = build(postings, scopes)
    assert files["summary-business.json"]["monthly"] == []


def test_business_expense_appears_in_both_views(scopes):
    """★家計ビューには事業の費用も出る。実際に家計から出ていったお金だから。"""
    postings = [p("Expenses:Business:Supplies", 12800)]
    files = build(postings, scopes)
    assert files["summary-business.json"]["monthly"][0]["expense"] == 12800
    assert files["summary-household.json"]["monthly"][0]["expense"] == 12800


def test_categories_carry_their_namespace(scopes):
    """名前空間が無いと、画面上で事業と家計の区別がつかない。"""
    postings = [
        p("Expenses:Business:Supplies", 12800),
        p("Expenses:Personal:Food:Groceries", 1580, txn="t2"),
    ]
    cats = build(postings, scopes)["categories-household.json"]["months"]["2026-07"]
    assert {c["namespace"] for c in cats} == {"business", "personal"}


def test_personal_assets_never_reach_the_business_view(scopes):
    postings = [p("Assets:Personal:Cash", 5000)]
    files = build(postings, scopes)
    assert files["accounts-business.json"]["accounts"] == []


# ── 数値の扱い ──────────────────────────────────────────


def test_income_is_reported_as_positive(scopes):
    """収入は元帳では貸方（負）。画面では正の額として出す。"""
    postings = [p("Income:Business:ClientA", -100000)]
    monthly = build(postings, scopes)["summary-household.json"]["monthly"][0]
    assert monthly["income"] == 100000


def test_net_is_income_minus_expense(scopes):
    postings = [
        p("Income:Business:ClientA", -100000),
        p("Expenses:Personal:Food:Groceries", 30000, txn="t2"),
    ]
    monthly = build(postings, scopes)["summary-household.json"]["monthly"][0]
    assert monthly["net"] == 70000


def test_ratios_sum_to_one(scopes):
    postings = [
        p("Expenses:Personal:Food:Groceries", 3000),
        p("Expenses:Personal:Transport:Train", 1000, txn="t2"),
    ]
    cats = build(postings, scopes)["categories-household.json"]["months"]["2026-07"]
    assert abs(sum(c["ratio"] for c in cats) - 1.0) < 0.001


def test_zero_total_does_not_divide_by_zero(scopes):
    assert build([], scopes)["categories-household.json"]["months"] == {}


def test_categories_are_ordered_by_amount(scopes):
    postings = [
        p("Expenses:Personal:Transport:Train", 460),
        p("Expenses:Personal:Food:Groceries", 6010, txn="t2"),
    ]
    cats = build(postings, scopes)["categories-household.json"]["months"]["2026-07"]
    assert [c["amount"] for c in cats] == [6010, 460]


# ── 対応が必要なもの（忘れられないように）───────────────


def test_pending_transactions_are_surfaced(scopes):
    postings = [p("Expenses:Personal:Food:Eatout", 950, pending=True)]
    assert build(postings, scopes)["attention.json"]["pending"]["count"] == 1


def test_documents_needing_review_are_surfaced(scopes):
    docs = [{"doc_id": "doc_x", "needs_review": True, "review_reason": "読めない"}]
    files = build([], scopes, docs)
    assert files["attention.json"]["needs_review"]["count"] == 1
    assert files["attention.json"]["needs_review"]["doc_ids"] == ["doc_x"]


# ── 出力の形 ────────────────────────────────────────────


def test_commit_is_recorded_for_printing(scopes):
    """★紙とリポジトリの状態を紐づけるため（第3部 §10）。"""
    assert build([], scopes)["meta.json"]["commit"] == "abc1234"


def test_output_is_deterministic(tmp_path, scopes):
    postings = [p("Expenses:Personal:Food:Groceries", 1580)]
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        build_web_data(
            postings=postings,
            documents=[],
            scopes=scopes,
            generated_at="2026-08-22T22:00:00+09:00",
            commit="abc1234",
        ).write(out)
    for name in sorted(x.name for x in a.iterdir()):
        assert (a / name).read_text(encoding="utf-8") == (b / name).read_text(encoding="utf-8")


def test_files_are_valid_json(tmp_path, scopes):
    written = build_web_data(
        postings=[p("Expenses:Personal:Food:Groceries", 1580)],
        documents=[],
        scopes=scopes,
        generated_at="2026-08-22T22:00:00+09:00",
    ).write(tmp_path)
    assert written
    for path in written:
        json.loads(path.read_text(encoding="utf-8"))


def test_transaction_keeps_its_postings_for_the_inspector(scopes):
    """★根拠インスペクタが仕訳の全行を見せるため（第3部 §7）。"""
    postings = [
        p("Expenses:Business:Supplies", 12800),
        p("Equity:Owner:Contributions", -12800),
        p("Assets:Personal:BusinessInterest", 12800),
        p("Liabilities:Personal:CreditCard:Sample", -12800),
    ]
    tx = build(postings, scopes)["transactions-household.json"]["transactions"][0]
    assert len(tx["postings"]) == 4
    assert sum(x["amount"] for x in tx["postings"]) == 0
