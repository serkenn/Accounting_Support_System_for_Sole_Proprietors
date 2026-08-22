"""口座・カードのマスタの検査。"""

from __future__ import annotations

import textwrap

import pytest

from shiwake.rules_check import check_accounts


def write(tmp_path, body: str):
    p = tmp_path / "accounts.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


CARD = """
    cards:
      - id: main
        namespace: mixed
        liability_account: "Liabilities:Personal:CreditCard:Main"
        card_last4: "1234"
        debit_account: "Assets:Personal:Bank:Main"
        closing_day: 15
        debit_day: 10
        verified_on: 2026-08-23
"""


def rules(issues):
    return [i.message for i in issues]


def test_verified_card_passes(tmp_path):
    assert check_accounts(write(tmp_path, CARD)) == []


def test_unverified_schedule_warns(tmp_path):
    """★調べただけの値を黙って信用しない。

    締め日が違うと資金繰りがズレるが、元帳の貸借は合うので検算では気づけない。
    """
    body = CARD.replace("verified_on: 2026-08-23", "verified_on: null")
    issues = check_accounts(write(tmp_path, body))
    assert issues and issues[0].severity == "warning"
    assert "明細で確認していません" in issues[0].message


def test_missing_schedule_warns(tmp_path):
    body = CARD.replace("closing_day: 15", "closing_day: null").replace(
        "debit_day: 10", "debit_day: null"
    )
    issues = check_accounts(write(tmp_path, body))
    assert any("予定日が出せません" in m for m in rules(issues))


def test_long_account_number_is_rejected(tmp_path):
    body = CARD.replace('card_last4: "1234"', 'card_last4: "1234567890123456"')
    issues = check_accounts(write(tmp_path, body))
    assert any(i.severity == "error" and "下4桁のみ" in i.message for i in issues)


def test_mixed_card_must_be_personal(tmp_path):
    """★混在は家計側に置く（Q3 の決定）。"""
    body = CARD.replace(
        '"Liabilities:Personal:CreditCard:Main"', '"Liabilities:Business:CreditCard:Main"'
    )
    issues = check_accounts(write(tmp_path, body))
    assert any("*:Personal:*" in m for m in rules(issues))


def test_business_card_may_be_business(tmp_path):
    body = CARD.replace("namespace: mixed", "namespace: business").replace(
        '"Liabilities:Personal:CreditCard:Main"', '"Liabilities:Business:CreditCard:Main"'
    )
    assert check_accounts(write(tmp_path, body)) == []


@pytest.mark.parametrize("bad", ["shared", "", "Business"])
def test_unknown_namespace_is_rejected(tmp_path, bad):
    body = CARD.replace("namespace: mixed", f'namespace: "{bad}"')
    issues = check_accounts(write(tmp_path, body))
    assert any(i.severity == "error" for i in issues)


def test_bank_entries_are_checked_too(tmp_path):
    body = """
        banks:
          - id: main
            namespace: mixed
            account: "Assets:Business:Bank:Main"
            account_no_last4: "1234"
    """
    issues = check_accounts(write(tmp_path, body))
    assert any("*:Personal:*" in m for m in rules(issues))


def test_missing_file_is_not_an_error(tmp_path):
    assert check_accounts(tmp_path / "absent.yaml") == []


def test_missing_debit_account_warns(tmp_path):
    """★引落口座が決まらないと、引落の仕訳そのものが作れない。

    締め日だけ分かっても、どこから落ちるか分からなければ元帳に書けない。
    """
    body = CARD.replace('debit_account: "Assets:Personal:Bank:Main"', "debit_account: null")
    issues = check_accounts(write(tmp_path, body))
    assert any("引落の仕訳が作れません" in i.message for i in issues)


def test_card_with_everything_unknown_warns_but_does_not_error(tmp_path):
    """★分からないものは null で置ける。埋めるまで警告が出続ける。

    推測で埋めるより、分からないまま警告が出ている方がよい。
    """
    body = """
        cards:
          - id: later
            namespace: mixed
            liability_account: "Liabilities:Personal:CreditCard:Later"
            card_last4: "1234"
            debit_account: null
            closing_day: null
            debit_day: null
            verified_on: null
    """
    issues = check_accounts(write(tmp_path, body))
    assert issues
    assert all(i.severity == "warning" for i in issues)
