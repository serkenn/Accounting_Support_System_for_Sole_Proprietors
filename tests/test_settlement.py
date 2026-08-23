"""即時払いの貸方を rules/accounts.yaml から引く。

★デビット・コード決済・電子マネーは負債を残さない。
  引落元をここで正しく引けないと、build がカード負債に落として
  **貸借は合ったまま**貸借対照表だけが間違う。
"""

from __future__ import annotations

import textwrap

from shiwake.ledger.settlement import load_settlement_accounts

ACCOUNTS = textwrap.dedent(
    """
    version: 1
    debit_cards:
      - id: debit_d
        name: "サンプル銀行 デビット"
        namespace: mixed
        card_last4: "1111"
        account: "Assets:Personal:Bank:G"
        settlement: immediate
        verified_on: 2026-08-23
        also_appears_as:
          - card_last4: "2222"
            seen_on: 2026-08-07
    prepaid:
      - id: suica
        name: "Suica"
        namespace: mixed
        account: "Assets:Personal:Prepaid:Suica"
    """
)


def _load(tmp_path, text=ACCOUNTS):
    p = tmp_path / "accounts.yaml"
    p.write_text(text, encoding="utf-8")
    return load_settlement_accounts(p)


def test_debit_card_resolves_to_its_bank(tmp_path):
    assert _load(tmp_path)["debit_card:1111"] == "Assets:Personal:Bank:G"


def test_alias_last4_resolves_to_the_same_bank(tmp_path):
    """★売上票に別の下4桁が出ても、同じ口座に行き着くこと。

    ここが引けないと、その支払いだけ引落元不明で止まる。
    """
    assert _load(tmp_path)["debit_card:2222"] == "Assets:Personal:Bank:G"


def test_prepaid_resolves_for_ic_card(tmp_path):
    assert _load(tmp_path)["ic_card:suica"] == "Assets:Personal:Prepaid:Suica"


def test_missing_file_gives_an_empty_map(tmp_path):
    assert load_settlement_accounts(tmp_path / "nope.yaml") == {}


def test_debit_card_without_an_account_is_skipped(tmp_path):
    """★account が無いものを既定値で埋めない。引けないほうが安全。"""
    text = textwrap.dedent(
        """
        debit_cards:
          - id: debit_x
            card_last4: "3333"
        """
    )
    assert _load(tmp_path, text) == {}


# ── コード決済（PayPay など）────────────────────────────


WALLETS = textwrap.dedent(
    """
    prepaid:
      - id: suica
        name: "Suica"
        account: "Assets:Personal:Prepaid:Suica"
      - id: samplepay
        name: "サンプルペイ"
        method: qr_code
        account: "Assets:Personal:Prepaid:SamplePay"
    """
)


def test_wallet_method_defaults_to_ic_card(tmp_path):
    assert _load(tmp_path, WALLETS)["ic_card:suica"] == "Assets:Personal:Prepaid:Suica"


def test_qr_wallet_is_keyed_by_its_method(tmp_path):
    out = _load(tmp_path, WALLETS)
    assert out["qr_code:samplepay"] == "Assets:Personal:Prepaid:SamplePay"
    assert "ic_card:samplepay" not in out


def test_a_sole_wallet_of_a_method_also_answers_the_bare_key(tmp_path):
    """★領収書に残高の名前が書かれていないことがある。

    その手段の残高が1つしかないなら曖昧さは無いので引けてよい。
    2つ以上あるときは引けない（どちらか分からないまま進めない）。
    """
    out = _load(tmp_path, WALLETS)
    assert out["qr_code"] == "Assets:Personal:Prepaid:SamplePay"
    assert out["ic_card"] == "Assets:Personal:Prepaid:Suica"


def test_two_wallets_of_one_method_leave_the_bare_key_unset(tmp_path):
    text = textwrap.dedent(
        """
        prepaid:
          - id: a
            method: qr_code
            account: "Assets:Personal:Prepaid:A"
          - id: b
            method: qr_code
            account: "Assets:Personal:Prepaid:B"
        """
    )
    out = _load(tmp_path, text)
    assert "qr_code" not in out
    assert out["qr_code:a"] == "Assets:Personal:Prepaid:A"
