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


# ── 種別ごとに要求するものが違う ────────────────────────


def test_debit_card_does_not_need_a_closing_day(tmp_path):
    """★デビットは即時支払。締め日も引落日も存在しない。

    クレジットと同じ検査を掛けると、無いものを要求する警告が出続ける。
    """
    body = """
        debit_cards:
          - id: debit_a
            namespace: mixed
            card_last4: "1234"
            account: "Assets:Personal:Bank:B"
            settlement: immediate
            verified_on: 2026-08-23
    """
    assert check_accounts(write(tmp_path, body)) == []


def test_prepaid_does_not_need_a_closing_day(tmp_path):
    body = """
        prepaid:
          - id: suica
            namespace: mixed
            account: "Assets:Personal:Prepaid:Suica"
    """
    assert check_accounts(write(tmp_path, body)) == []


def test_debit_card_is_still_checked_for_namespace_and_last4(tmp_path):
    """締め日は不要だが、名前空間と下4桁の規則は同じように効く。"""
    body = """
        debit_cards:
          - id: debit_a
            namespace: mixed
            card_last4: "12345678"
            account: "Assets:Business:Bank:B"
    """
    issues = check_accounts(write(tmp_path, body))
    assert any("下4桁のみ" in i.message for i in issues)
    assert any("*:Personal:*" in i.message for i in issues)


def test_debit_card_account_must_be_verified(tmp_path):
    """★引落元が違うと、そのカードの支払いが全部まちがった口座から出る。

    しかも元帳の貸借は合うので、検算では気づけない。
    """
    body = """
        debit_cards:
          - id: debit_a
            namespace: mixed
            card_last4: "1234"
            account: "Assets:Personal:Bank:B"
            verified_on: null
    """
    issues = check_accounts(write(tmp_path, body))
    assert any("まちがった口座" in i.message for i in issues)


def test_verified_debit_card_passes(tmp_path):
    body = """
        debit_cards:
          - id: debit_a
            namespace: mixed
            card_last4: "1234"
            account: "Assets:Personal:Bank:B"
            verified_on: 2026-08-23
    """
    assert check_accounts(write(tmp_path, body)) == []


def test_debit_card_without_account_is_an_error(tmp_path):
    body = """
        debit_cards:
          - id: debit_a
            namespace: mixed
            card_last4: "1234"
            account: null
    """
    issues = check_accounts(write(tmp_path, body))
    assert any(i.severity == "error" for i in issues)
