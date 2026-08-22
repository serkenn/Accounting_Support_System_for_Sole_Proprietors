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

# ★公開側のテストは公開側だけで完結させる（第13部 §5）。
#   非公開リポジトリを参照すると、それが無い環境で落ちる。
RULES = Path(__file__).resolve().parents[1] / "templates" / "scopes.yaml"


@pytest.fixture
def scopes():
    return load_scopes(RULES)


def p(account, amount, d=(2026, 7, 14), payee="サンプルストア", txn="t1", **kw):
    return LedgerPosting(
        date=date(*d), payee=payee, narration="", account=account, amount=amount, txn_id=txn, **kw
    )


def paid(account, amount, wallet="Assets:Personal:Cash", d=(2026, 7, 14), txn="t1"):
    """費用と、その支払い元の財布を対で作る。

    ★家計の支出は財布の増減で数えるので、片側だけの posting では
      「財布から出ていない」ことになる。実際の仕訳の形で書く。
    """
    return [
        p(account, amount, d=d, txn=txn),
        p(wallet, -amount, d=d, txn=txn),
    ]


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
    """★家計の財布から出たなら、家計ビューにも出る。

    出どころが事業用口座なら家計には出ない
    （test_business_expense_from_a_business_account_is_not_household_spending）。
    """
    postings = paid("Expenses:Business:Supplies", 12800, "Liabilities:Personal:CreditCard:Sample")
    files = build(postings, scopes)
    assert files["summary-business.json"]["monthly"][0]["expense"] == 12800
    assert files["summary-household.json"]["monthly"][0]["expense"] == 12800


def test_categories_carry_their_namespace(scopes):
    """名前空間が無いと、画面上で事業と家計の区別がつかない。"""
    postings = [
        *paid("Expenses:Business:Supplies", 12800, "Liabilities:Personal:CreditCard:Sample"),
        *paid("Expenses:Personal:Food:Groceries", 1580, txn="t2"),
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
    postings = [
        p("Assets:Personal:Bank:Sample", 100000),
        p("Income:Business:ClientA", -100000),
    ]
    monthly = build(postings, scopes)["summary-household.json"]["monthly"][0]
    assert monthly["income"] == 100000


def test_net_is_income_minus_expense(scopes):
    postings = [
        p("Assets:Personal:Bank:Sample", 100000),
        p("Income:Business:ClientA", -100000),
        *paid("Expenses:Personal:Food:Groceries", 30000, "Assets:Personal:Bank:Sample", txn="t2"),
    ]
    monthly = build(postings, scopes)["summary-household.json"]["monthly"][0]
    assert monthly["net"] == 70000


def test_ratios_sum_to_one(scopes):
    postings = [
        *paid("Expenses:Personal:Food:Groceries", 3000),
        *paid("Expenses:Personal:Transport:Train", 1000, txn="t2"),
    ]
    cats = build(postings, scopes)["categories-household.json"]["months"]["2026-07"]
    assert abs(sum(c["ratio"] for c in cats) - 1.0) < 0.001


def test_zero_total_does_not_divide_by_zero(scopes):
    assert build([], scopes)["categories-household.json"]["months"] == {}


def test_categories_are_ordered_by_amount(scopes):
    postings = [
        *paid("Expenses:Personal:Transport:Train", 460),
        *paid("Expenses:Personal:Food:Groceries", 6010, txn="t2"),
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


def test_default_month_skips_a_nearly_empty_trailing_month(scopes):
    """★月初に1件だけ入った翌月を既定で開くと、実質空の画面になる。

    「壊れている」ように見えるので、取引のある月を既定にする。
    """
    postings = [
        p("Expenses:Personal:Food:Groceries", 1000, (2026, 7, 3), txn="a"),
        p("Expenses:Personal:Food:Eatout", 680, (2026, 7, 5), txn="b"),
        p("Expenses:Personal:Transport:Train", 460, (2026, 7, 9), txn="c"),
        p("Expenses:Personal:Food:Eatout", 950, (2026, 8, 2), txn="d"),
    ]
    files = build(postings, scopes)
    assert files["meta.json"]["latest_month"] == "2026-07"
    # 月の一覧には両方入る（切り替えられる）
    assert files["meta.json"]["months"] == ["2026-07", "2026-08"]


def test_single_month_is_still_the_default(scopes):
    postings = [p("Expenses:Personal:Food:Eatout", 950, (2026, 8, 2))]
    assert build(postings, scopes)["meta.json"]["latest_month"] == "2026-08"


# ── 家計の支出は「財布から出た額」（第5部 §9.1）─────────
#
# ★何に使ったか（借方）ではなく、どの財布から出たか（貸方）で数える。
#   借方で数えると、事業用口座を分けた瞬間に家計の支出が過大になる。


def test_business_expense_from_a_business_account_is_not_household_spending(scopes):
    """★これが直した本体。家計の財布から1円も出ていない。"""
    postings = [
        p("Expenses:Business:Supplies", 50000, txn="biz"),
        p("Assets:Business:Bank:Sample", -50000, txn="biz"),
        p("Expenses:Personal:Food:Groceries", 10000, txn="home"),
        p("Assets:Personal:Bank:Sample", -10000, txn="home"),
    ]
    monthly = build(postings, scopes)["summary-household.json"]["monthly"][0]
    assert monthly["expense"] == 10000


def test_business_expense_from_a_personal_card_is_household_spending(scopes):
    """混在カードなら家計の財布から出ている。これは家計の支出。"""
    postings = [
        p("Expenses:Business:Supplies", 12800),
        p("Equity:Owner:Contributions", -12800),
        p("Assets:Personal:BusinessInterest", 12800),
        p("Liabilities:Personal:CreditCard:Sample", -12800),
    ]
    monthly = build(postings, scopes)["summary-household.json"]["monthly"][0]
    assert monthly["expense"] == 12800
    # ★同額が事業への持分に変わっている。目減りではない
    assert monthly["business_share"] == 12800


def test_business_interest_is_not_a_wallet(scopes):
    """★持分は財布ではない。ここを財布に数えると出入りが 0 になる。"""
    assert not scopes.is_wallet("Assets:Personal:BusinessInterest")
    assert scopes.is_wallet("Assets:Personal:Bank:Sample")
    assert scopes.is_wallet("Liabilities:Personal:CreditCard:Sample")


def test_prepaid_tax_is_not_a_wallet(scopes):
    """天引きされた税金は使えるお金ではない。"""
    assert not scopes.is_wallet("Assets:Personal:PrepaidTax:Withholding")


def test_transfer_between_wallets_is_not_spending(scopes):
    """★カードの引落は財布どうしの振替。支出はカードを使った時点で計上済み。"""
    postings = [
        p("Liabilities:Personal:CreditCard:Sample", 31850),
        p("Assets:Personal:Bank:Sample", -31850),
    ]
    monthly = build(postings, scopes)["summary-household.json"]["monthly"]
    assert monthly == [] or monthly[0]["expense"] == 0


def test_salary_is_counted_as_take_home(scopes):
    """第5部 §9.1 — 家計の収入は手取りで出す。"""
    postings = [
        p("Assets:Personal:Bank:Sample", 98400),
        p("Assets:Personal:PrepaidTax:Withholding", 2400),
        p("Expenses:Personal:SocialInsurance", 14200),
        p("Expenses:Personal:ResidentTax", 5000),
        p("Income:Employment:Sample", -120000),
    ]
    monthly = build(postings, scopes)["summary-household.json"]["monthly"][0]
    assert monthly["income"] == 98400
    # 天引き分は財布を通っていないので、支出にも出ない（二重に数えない）
    assert monthly["expense"] == 0


def test_categories_split_the_outflow_without_losing_yen(scopes):
    """按分の端数で1円も失わないこと。"""
    postings = [
        p("Expenses:Personal:Food:Groceries", 333),
        p("Expenses:Personal:Transport:Train", 333),
        p("Expenses:Personal:Misc", 334),
        p("Assets:Personal:Cash", -1000),
    ]
    files = build(postings, scopes)
    cats = files["categories-household.json"]["months"]["2026-07"]
    assert sum(c["amount"] for c in cats) == 1000
    assert files["summary-household.json"]["monthly"][0]["expense"] == 1000


def test_business_view_still_uses_accrual(scopes):
    """★事業ビューは決算書の範囲なので、発生ベースのまま。数え方が違う。"""
    postings = [
        p("Expenses:Business:Supplies", 50000, txn="biz"),
        p("Assets:Business:Bank:Sample", -50000, txn="biz"),
    ]
    monthly = build(postings, scopes)["summary-business.json"]["monthly"][0]
    assert monthly["expense"] == 50000


def test_opening_balance_is_not_income(scopes):
    """★期首残高は「入ってきたお金」ではない。

    最初から持っていたものを宣言しているだけ。
    ここを数えると、初月の収入が期首残高の分だけ跳ね上がる。
    """
    postings = [
        p("Assets:Personal:Bank:Sample", 200000, txn="open"),
        p("Assets:Personal:Cash", 5000, txn="open"),
        p("Equity:Opening-Balances", -205000, txn="open"),
        *paid("Expenses:Personal:Food:Groceries", 1000, txn="buy"),
    ]
    monthly = build(postings, scopes)["summary-household.json"]["monthly"][0]
    assert monthly["income"] == 0
    assert monthly["expense"] == 1000
