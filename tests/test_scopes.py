"""所得区分と名前空間の検査（第5部 §11 / 第10部 §8）。

所得区分の取り違えは申告の誤りに直結する。給与を事業の売上に入れれば
所得を過大に申告し、奨学金を所得に入れれば扶養の判定まで狂う。
人の注意力ではなく、ここで機械的に止める。
"""

from __future__ import annotations

import textwrap

import pytest

from shiwake import scopes as sc

RULES = textwrap.dedent(
    """
    version: 1
    scopes:
      business:
        label: 事業
        include: ["Assets:Business:*", "Income:Business:*", "Expenses:Business:*", "Equity:Owner:*"]
      household:
        label: 家計
        include: ["*"]
    guards:
      - id: no_employment_income_in_business
        aggregate: business_pl
        forbid: "Income:Employment:*"
        severity: error
        reason: 給与所得は事業所得ではない
      - id: no_scholarship_in_total_income
        aggregate: total_income
        forbid: "Income:Other:Scholarship:*"
        severity: error
        reason: 給付型奨学金は非課税
    aggregates:
      business_pl:
        label: 事業の損益
        allow: ["Income:Business:*", "Expenses:Business:*"]
      total_income:
        label: 合計所得金額
        allow: ["Income:Business:*", "Expenses:Business:*", "Income:Employment:*"]
    crossing:
      namespaces: ["Business", "Personal"]
      bridge_equity: "Equity:Owner:*"
      bridge_asset: "Assets:Personal:BusinessInterest"
    """
)


@pytest.fixture
def rules(tmp_path):
    p = tmp_path / "scopes.yaml"
    p.write_text(RULES, encoding="utf-8")
    return sc.load_scopes(p)


# ── パターンの一致 ──────────────────────────────────────


@pytest.mark.parametrize(
    ("pattern", "account", "expected"),
    [
        ("Income:Business:*", "Income:Business:ClientA", True),
        ("Income:Business:*", "Income:Business", True),
        ("Income:Business:*", "Income:Employment:ShopA", False),
        ("*", "anything:at:all", True),
        ("*:Personal:*", "Assets:Personal:Cash", True),
        ("*:Personal:*", "Assets:Business:Cash", False),
        ("Equity:Owner:*", "Equity:Owner:Drawings", True),
        # 前方一致が語の途中で当たらないこと
        ("Income:Business:*", "Income:BusinessOther:X", False),
        ("Expenses:Business:Taxes", "Expenses:Business:TaxesExtra", False),
    ],
)
def test_pattern_matching(pattern, account, expected):
    assert sc.matches(pattern, account) is expected


# ── ビューの範囲 ────────────────────────────────────────


def test_business_scope_excludes_salary(rules):
    assert not rules.in_scope("business", "Income:Employment:ShopA")


def test_business_scope_excludes_personal_assets(rules):
    assert not rules.in_scope("business", "Assets:Personal:Cash")


def test_business_scope_includes_owner_equity(rules):
    assert rules.in_scope("business", "Equity:Owner:Drawings")


def test_household_scope_includes_everything(rules):
    for account in (
        "Income:Employment:ShopA",
        "Assets:Business:Cash",
        "Income:Other:Scholarship:Grant",
    ):
        assert rules.in_scope("household", account)


# ── 混入の検出 ──────────────────────────────────────────


def test_salary_in_business_pl_is_an_error(rules):
    issues = rules.check_aggregate("business_pl", ["Income:Business:A", "Income:Employment:ShopA"])
    assert [i.guard for i in issues] == ["no_employment_income_in_business"]
    assert issues[0].severity == "error"


def test_scholarship_in_total_income_is_an_error(rules):
    issues = rules.check_aggregate("total_income", ["Income:Other:Scholarship:Grant"])
    assert any(i.guard == "no_scholarship_in_total_income" for i in issues)


def test_clean_aggregate_has_no_issues(rules):
    assert (
        rules.check_aggregate("business_pl", ["Income:Business:A", "Expenses:Business:Travel"])
        == []
    )


def test_account_outside_allow_list_is_reported(rules):
    """★forbid だけだと、新しい科目が増えたときに黙って混入する。"""
    issues = rules.check_aggregate("business_pl", ["Assets:Business:Cash"])
    assert any(i.guard == "not_allowed" for i in issues)


def test_reason_is_included_so_the_message_teaches(rules):
    issues = rules.check_aggregate("business_pl", ["Income:Employment:ShopA"])
    assert "事業所得" in issues[0].message


# ── 名前空間をまたぐ仕訳 ────────────────────────────────


def _tx(accounts, amounts=None):
    amounts = amounts or [0] * len(accounts)
    return [
        sc.Posting("t1", a, n, "f.beancount", i + 1)
        for i, (a, n) in enumerate(zip(accounts, amounts, strict=True))
    ]


def test_crossing_without_a_bridge_is_an_error(rules):
    postings = _tx(["Expenses:Business:Supplies", "Assets:Personal:Cash"], [1000, -1000])
    issues = rules.check_crossings(postings)
    assert any(i.guard == "crossing_without_bridge" for i in issues)


def test_crossing_with_a_bridge_is_accepted(rules):
    postings = _tx(
        [
            "Expenses:Business:Supplies",
            "Equity:Owner:Contributions",
            "Assets:Personal:BusinessInterest",
            "Liabilities:Personal:CreditCard:Sample",
        ],
        [12800, -12800, 12800, -12800],
    )
    assert rules.check_crossings(postings) == []


def test_transaction_within_one_namespace_is_fine(rules):
    postings = _tx(["Expenses:Personal:Food:Groceries", "Assets:Personal:Cash"], [1000, -1000])
    assert rules.check_crossings(postings) == []


def test_business_only_transaction_is_fine(rules):
    postings = _tx(["Expenses:Business:Travel", "Assets:Business:Cash"], [1000, -1000])
    assert rules.check_crossings(postings) == []


# ── 不変条件 ────────────────────────────────────────────


def test_invariant_holds_for_balanced_bridges(rules):
    postings = _tx(
        ["Assets:Personal:BusinessInterest", "Equity:Owner:Contributions"], [12800, -12800]
    )
    assert rules.check_invariant(postings) == []


def test_invariant_detects_a_broken_bridge(rules):
    """★ここが崩れると名前空間の分離が意味を失う。"""
    postings = _tx(
        ["Assets:Personal:BusinessInterest", "Equity:Owner:Contributions"], [12800, -9000]
    )
    issues = rules.check_invariant(postings)
    assert any(i.guard == "bridge_invariant" for i in issues)


def test_invariant_on_empty_ledger(rules):
    assert rules.check_invariant([]) == []
