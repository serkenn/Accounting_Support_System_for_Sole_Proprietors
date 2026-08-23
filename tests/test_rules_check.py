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


def test_unknown_key_is_an_error(tmp_path):
    """★タイポで設定が黙って無効になるのを止める。

    実際に一括置換で debit_day が別の名前に化け、締め日の設定が
    効かなくなった。YAML は知らないキーを黙って受け取るので、
    ここで見るしかない。
    """
    body = CARD.replace("closing_day: 15", "closing_day: 15\n        debit_cay: 10")
    issues = check_accounts(write(tmp_path, body))
    assert any(i.severity == "error" and "知らないキー" in i.message for i in issues)


def test_known_keys_pass(tmp_path):
    assert check_accounts(write(tmp_path, CARD)) == []


def test_contactless_is_recorded_under_the_card_not_separately(tmp_path):
    """★非接触決済の下4桁はカード本体と違う。

    レシートには非接触側の下4桁が出るのに、請求はカード本体にまとまる。
    別のカードとして登録すると、同じ支払いを2つの口座に振り分けてしまう。
    """
    body = CARD.replace(
        "        verified_on: 2026-08-23",
        "        verified_on: 2026-08-23\n"
        "        contactless:\n"
        "          - brand: iD\n"
        '            card_last4: "5678"',
    )
    assert check_accounts(write(tmp_path, body)) == []


def test_contactless_last4_is_validated(tmp_path):
    body = CARD.replace(
        "        verified_on: 2026-08-23",
        "        verified_on: 2026-08-23\n"
        "        contactless:\n"
        "          - brand: iD\n"
        '            card_last4: "12345678"',
    )
    issues = check_accounts(write(tmp_path, body))
    assert any("下4桁のみ" in i.message for i in issues)


# ── トップレベルのタイポ（実際に起きた）─────────────────


def test_unknown_top_level_key_is_rejected(tmp_path):
    """★`debit_cards:` を `debit_dards:` と書いていた。

    キーごと綴りを間違えると data.get() が None を返し、その節が
    まるごと検査されない。**エラーも警告も出ないまま素通りする**ので、
    「検査が通った」ことが何の保証にもならなくなる。

    エントリの中のキーは既に弾いている。同じ理由で外側も弾く。
    """
    p = tmp_path / "accounts.yaml"
    p.write_text(
        "banks: []\ndebit_dards:\n  - id: debit_a\n    name: x\n",
        encoding="utf-8",
    )
    issues = check_accounts(p)
    assert any(i.severity == "error" and "debit_dards" in i.message for i in issues)


def test_known_top_level_keys_are_accepted(tmp_path):
    p = tmp_path / "accounts.yaml"
    p.write_text(
        "banks: []\ncards: []\ndebit_cards: []\nprepaid: []\ncash:\n  personal: A\n",
        encoding="utf-8",
    )
    assert not any("知らない節" in i.message for i in check_accounts(p))


def test_empty_accounts_file_is_fine(tmp_path):
    p = tmp_path / "accounts.yaml"
    p.write_text("", encoding="utf-8")
    assert check_accounts(p) == []


# ── 同じカードが別の下4桁で売上票に出る ─────────────────


def _debit(extra: str = "") -> str:
    return (
        "version: 1\n"
        "debit_cards:\n"
        "  - id: debit_d\n"
        '    name: "d"\n'
        "    namespace: mixed\n"
        '    card_last4: "1111"\n'
        '    account: "Assets:Personal:Bank:G"\n'
        "    settlement: immediate\n"
        "    verified_on: 2026-08-23\n" + extra
    )


def test_version_is_a_known_section(tmp_path):
    p = tmp_path / "accounts.yaml"
    p.write_text(_debit(), encoding="utf-8")
    assert not any("知らない節" in i.message for i in check_accounts(p))


def test_alias_last4_is_accepted(tmp_path):
    """★同じカードが店の売上票に別の下4桁で出ることがある。

    別カードとして登録すると1つの支払いが2つの口座に分かれ、
    どちらの残高も合わなくなる。同じカードの別名として持たせる。
    """
    p = tmp_path / "accounts.yaml"
    p.write_text(
        _debit('    also_appears_as:\n      - card_last4: "2222"\n        seen_on: 2026-08-07\n'),
        encoding="utf-8",
    )
    assert [i for i in check_accounts(p) if i.severity == "error"] == []


def test_alias_must_be_exactly_four_digits(tmp_path):
    """下4桁を超える桁を持たせない（第1部 §9.1）。

    ★桁あふれの例に「カード番号らしい長さ」を書かないこと。
      公開リポジトリにカード番号の形をした文字列を置くと、
      合成値でも redact-check が止める（止まるのが正しい）。
      5桁で同じ規則を試せる。
    """
    p = tmp_path / "accounts.yaml"
    p.write_text(
        _debit('    also_appears_as:\n      - card_last4: "12345"\n        seen_on: 2026-08-07\n'),
        encoding="utf-8",
    )
    assert any(i.severity == "error" for i in check_accounts(p))


def test_alias_requires_the_date_it_was_seen(tmp_path):
    """★いつの証憑で確認したかが無いと、あとで裏を取れない。"""
    p = tmp_path / "accounts.yaml"
    p.write_text(
        _debit('    also_appears_as:\n      - card_last4: "2222"\n'),
        encoding="utf-8",
    )
    assert any(i.severity == "error" for i in check_accounts(p))


def test_alias_must_not_collide_with_another_card(tmp_path):
    """★別カードの下4桁を別名にすると、支払いの帰属が二重になる。"""
    p = tmp_path / "accounts.yaml"
    p.write_text(
        "version: 1\n"
        "cards:\n"
        "  - id: card_b\n"
        '    name: "b"\n'
        "    namespace: mixed\n"
        '    card_last4: "3333"\n'
        '    liability_account: "Liabilities:Personal:CreditCard:B"\n'
        '    debit_account: "Assets:Personal:Bank:A"\n'
        "    closing_day: 15\n"
        "    debit_day: 10\n"
        "    debit_month_offset: 1\n"
        "    verified_on: 2026-08-23\n"
        + _debit(
            '    also_appears_as:\n      - card_last4: "3333"\n        seen_on: 2026-08-07\n'
        ).split("version: 1\n")[1],
        encoding="utf-8",
    )
    issues = check_accounts(p)
    assert any(i.severity == "error" and "3333" in i.message for i in issues)
