"""元帳生成（第1部 §6）。★二重計上を構造的に防ぐのがここ。"""

from __future__ import annotations

from datetime import date

from shiwake.ledger.build import build_month, card_debit_transaction
from shiwake.ledger.categorize import Categorizer, CategoryRule
from shiwake.ledger.merchants import Merchant, MerchantIndex
from shiwake.ledger.reconcile import CardLine, Links, Receipt

INDEX = MerchantIndex(
    [
        Merchant(id="store", canonical="サンプルストア", aliases=("サンプルストア ワタダ",)),
        Merchant(id="denki", canonical="サンプル電機", aliases=("サンプルデンキ",)),
    ]
)
CAT = Categorizer(
    [
        CategoryRule(
            id="groceries", account="Expenses:Personal:Food:Groceries", merchant_id="store"
        ),
        CategoryRule(
            id="supplies", account="Expenses:Business:Supplies", merchant_id="denki", business=True
        ),
    ],
    INDEX,
)
CARD = "Liabilities:Personal:CreditCard:Sample"


def line(line_id="L001", d=(2026, 7, 14), desc="サンプルストア ワタダ", amount=1234):
    return CardLine("doc_stmt", CARD, line_id, date(*d), desc, amount)


def receipt(
    doc_id="doc_r1", d=(2026, 7, 14), issuer="サンプルストア", total=1234, method="credit_card"
):
    return Receipt(doc_id, date(*d), issuer, total, method)


# ── 二重計上の防止 ──────────────────────────────────────


def test_linked_pair_produces_exactly_one_transaction():
    """★心臓部。同じ支出を2件の仕訳にしない。"""
    links = Links("2026-07", {"doc_r1": "doc_stmt:L001"})
    r = build_month([receipt()], [line()], links, CAT)
    assert len(r.transactions) == 1


def test_expense_total_equals_card_statement_total():
    """★受け入れ条件。カード払いの合計が請求総額と一致する。"""
    lines = [line("L001", amount=1000), line("L002", (2026, 7, 20), amount=2000)]
    receipts = [receipt("doc_a", total=1000)]
    links = Links("2026-07", {"doc_a": "doc_stmt:L001"})
    r = build_month(receipts, lines, links, CAT)
    charged = sum(
        -p.amount
        for t in r.transactions
        for p in t.postings
        if p.account == CARD and p.amount is not None
    )
    inferred = sum(t.balance() for t in r.transactions if any(p.amount is None for p in t.postings))
    assert charged + inferred == 3000


def test_unlinked_card_line_still_produces_a_transaction():
    r = build_month([], [line()], Links("2026-07"), CAT)
    assert len(r.transactions) == 1
    assert r.transactions[0].meta["card_line"] == "doc_stmt:L001"


# ── 優先順位（第1部 §6）─────────────────────────────────


def test_card_line_is_the_source_of_truth_for_amount_and_date():
    links = Links("2026-07", {"doc_r1": "doc_stmt:L001"})
    r = build_month([receipt(d=(2026, 7, 12))], [line(d=(2026, 7, 14))], links, CAT)
    assert r.transactions[0].date == date(2026, 7, 14)


def test_linked_amounts_must_agree():
    """リンク先と額が違うのは、リンクが間違っている。黙って通さない。"""
    links = Links("2026-07", {"doc_r1": "doc_stmt:L001"})
    r = build_month([receipt(total=999)], [line(amount=1234)], links, CAT)
    assert r.errors


def test_cash_receipt_credits_cash():
    r = build_month([receipt(method="cash")], [], Links("2026-07"), CAT)
    assert r.transactions[0].postings[-1].account == "Assets:Personal:Cash"


def test_card_receipt_without_statement_is_pending():
    """明細が届いたらリンクされ、pending が外れる（第1部 §6）。"""
    r = build_month([receipt()], [], Links("2026-07"), CAT)
    t = r.transactions[0]
    assert t.meta["pending"] == "TRUE"
    assert "pending" in t.tags


def test_tags_are_ascii():
    """★Beancount のタグに日本語は使えない。"""
    r = build_month([receipt()], [], Links("2026-07"), CAT)
    for t in r.transactions:
        for tag in t.tags:
            assert tag.isascii()


# ── 名前空間をまたぐ仕訳（Q2 の Model A）────────────────


def test_business_expense_on_a_personal_card_gets_a_bridge():
    """★混在カードで事業の買い物。必ずこの形になる。"""
    r = build_month([], [line(desc="サンプルデンキ", amount=12800)], Links("2026-07"), CAT)
    accounts = {p.account for p in r.transactions[0].postings}
    assert "Equity:Owner:Contributions" in accounts
    assert "Assets:Personal:BusinessInterest" in accounts


def test_bridged_transaction_balances():
    r = build_month([], [line(desc="サンプルデンキ", amount=12800)], Links("2026-07"), CAT)
    assert r.transactions[0].balance() == 0


def test_personal_expense_needs_no_bridge():
    r = build_month([], [line()], Links("2026-07"), CAT)
    accounts = {p.account for p in r.transactions[0].postings}
    assert "Equity:Owner:Contributions" not in accounts


def test_bridge_invariant_holds_across_the_month():
    """★持分と資本の合計がゼロ（Phase 12 の不変条件）。"""
    lines = [
        line("L001", amount=1000),
        line("L002", (2026, 7, 20), "サンプルデンキ", 12800),
        line("L003", (2026, 7, 25), "サンプルデンキ", 4500),
    ]
    r = build_month([], lines, Links("2026-07"), CAT)
    total = sum(
        p.amount
        for t in r.transactions
        for p in t.postings
        if p.amount is not None
        and (
            p.account.startswith("Equity:Owner") or p.account == "Assets:Personal:BusinessInterest"
        )
    )
    assert total == 0


# ── 分類できないものを黙って通さない ────────────────────


def test_unknown_merchant_is_an_error_not_a_guess():
    r = build_month([], [line(desc="見たことのない店")], Links("2026-07"), CAT)
    assert r.transactions == []
    assert r.errors and "rules/categories.yaml" in r.errors[0].message


# ── 引落 ────────────────────────────────────────────────


def test_card_debit_balances():
    t = card_debit_transaction(
        date(2026, 8, 27), "カード引落", CARD, "Assets:Personal:Bank:Sample", 31850
    )
    assert t.balance() == 0
    assert t.postings[0].amount == 31850


# ── 出力 ────────────────────────────────────────────────


def test_rendered_output_is_stable():
    lines = [line("L002", (2026, 7, 20)), line("L001", (2026, 7, 14))]
    first = build_month([], lines, Links("2026-07"), CAT).render()
    second = build_month([], list(reversed(lines)), Links("2026-07"), CAT).render()
    assert first == second


def test_amounts_are_rendered_with_separators():
    r = build_month([], [line(amount=1234567)], Links("2026-07"), CAT)
    assert "1,234,567 JPY" in r.transactions[0].render()
