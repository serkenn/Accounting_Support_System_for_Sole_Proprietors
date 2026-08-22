"""決算書マッピングの網羅性（第2部 §7.2）。"""

from __future__ import annotations

import textwrap

import pytest
import yaml

from shiwake.tax import check_mapping_coverage

MAPPING = yaml.safe_load(
    textwrap.dedent(
        """
        損益計算書:
          売上（収入）金額: ["Income:Business:*"]
          水道光熱費:       ["Expenses:Business:Utilities:*"]
          旅費交通費:       ["Expenses:Business:Travel"]
          雑費:             ["Expenses:Business:Misc", "Expenses:Business:BankFee"]
        貸借対照表:
          現金:             ["Assets:Business:Cash"]
        除外:
          - "Expenses:Personal:*"
        """
    )
)


def test_mapped_account_passes():
    assert check_mapping_coverage(["Expenses:Business:Travel"], MAPPING) == []


def test_wildcard_mapping_covers_children():
    assert check_mapping_coverage(["Expenses:Business:Utilities:Electricity"], MAPPING) == []


def test_several_accounts_on_one_line_is_fine():
    accounts = ["Expenses:Business:Misc", "Expenses:Business:BankFee"]
    assert check_mapping_coverage(accounts, MAPPING) == []


def test_unmapped_expense_is_an_error():
    """★これが本命。費目を足してマッピングを忘れると P/L から黙って落ちる。"""
    issues = check_mapping_coverage(["Expenses:Business:Advertising"], MAPPING)
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "黙って落ちます" in issues[0].message


def test_account_mapped_twice_is_an_error():
    mapping = {
        "損益計算書": {
            "通信費": ["Expenses:Business:Communication"],
            "雑費": ["Expenses:Business:*"],
        }
    }
    issues = check_mapping_coverage(["Expenses:Business:Communication"], mapping)
    assert issues and "二重計上" in issues[0].message


def test_non_business_expenses_are_not_required():
    assert check_mapping_coverage(["Expenses:Personal:Food:Groceries"], MAPPING) == []


def test_empty_ledger_is_fine():
    assert check_mapping_coverage([], MAPPING) == []


@pytest.mark.parametrize("require", ["Income:Business:*", "Assets:Business:*"])
def test_scope_of_the_check_is_configurable(require):
    assert (
        check_mapping_coverage(["Income:Business:A", "Assets:Business:Cash"], MAPPING, require)
        == []
    )
