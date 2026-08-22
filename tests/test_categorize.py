"""勘定科目の自動分類（第1部 §6）。"""

from __future__ import annotations

import textwrap

import pytest

from shiwake.ledger.categorize import load_categories
from shiwake.ledger.merchants import Merchant, MerchantIndex

INDEX = MerchantIndex(
    [
        Merchant(id="store", canonical="サンプルストア", aliases=("サンプルストア ワタダ",)),
        Merchant(id="denki", canonical="サンプル電機"),
    ]
)

RULES = textwrap.dedent(
    """
    version: 1
    rules:
      - id: groceries
        match: { merchant_id: store }
        account: "Expenses:Personal:Food:Groceries"
      - id: hardware_business
        match: { merchant_id: denki }
        account: "Expenses:Business:Supplies"
        business: true
      - id: rail
        match: { pattern: "jr|鉄道|地下鉄" }
        account: "Expenses:Personal:Transport:Train"
    """
)


@pytest.fixture
def cat(tmp_path):
    p = tmp_path / "categories.yaml"
    p.write_text(RULES, encoding="utf-8")
    return load_categories(p, INDEX)


def test_merchant_rule_matches(cat):
    result = cat.categorize("サンプルストア ワタダ")
    assert result.account == "Expenses:Personal:Food:Groceries"
    assert result.rule_id == "groceries"
    assert not result.business


def test_business_flag_is_carried(cat):
    result = cat.categorize("サンプル電機")
    assert result.account == "Expenses:Business:Supplies"
    assert result.business


def test_pattern_rule_matches(cat):
    assert cat.categorize("JR東日本 乗車").account == "Expenses:Personal:Transport:Train"


def test_pattern_is_applied_after_normalization(cat):
    """全角や大文字の揺れをルール側で吸収しなくてよい。"""
    assert cat.categorize("ＪＲ東日本").account == "Expenses:Personal:Transport:Train"


def test_unknown_merchant_is_left_unresolved(cat):
    """★「その他」に落とさない。落とすと分類漏れに気づけなくなる。"""
    result = cat.categorize("見たことのない店")
    assert result.account is None
    assert not result.resolved


def test_empty_description_is_unresolved(cat):
    assert not cat.categorize(None).resolved


def test_rules_are_applied_in_order(tmp_path):
    rules = textwrap.dedent(
        """
        version: 1
        rules:
          - id: first
            match: { pattern: "サンプル" }
            account: "Expenses:Personal:Misc"
          - id: second
            match: { merchant_id: store }
            account: "Expenses:Personal:Food:Groceries"
        """
    )
    p = tmp_path / "c.yaml"
    p.write_text(rules, encoding="utf-8")
    assert load_categories(p, INDEX).categorize("サンプルストア").rule_id == "first"


def test_missing_file_resolves_nothing(tmp_path):
    cat = load_categories(tmp_path / "absent.yaml", INDEX)
    assert not cat.categorize("サンプルストア").resolved
