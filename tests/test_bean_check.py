"""`bean-check` の呼び出し（D57 — サブプロセス限定）。"""

from __future__ import annotations

import textwrap

import pytest

from shiwake.ledger import bean_check, bean_check_available
from shiwake.ledger.check import BeanCheckMissingError

pytestmark = pytest.mark.skipif(not bean_check_available(), reason="bean-check が未インストール")


def _write(tmp_path, content: str):
    p = tmp_path / "main.beancount"
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return p


BALANCED = """
    2026-08-01 open Assets:Personal:Bank:Sample JPY
    2026-08-01 open Expenses:Personal:Food:Groceries JPY

    2026-08-14 * "サンプルストア" "食料品"
      Expenses:Personal:Food:Groceries   1000 JPY
      Assets:Personal:Bank:Sample       -1000 JPY
"""


def test_balanced_ledger_passes(tmp_path):
    assert bean_check(_write(tmp_path, BALANCED)).ok


def test_unbalanced_ledger_fails(tmp_path):
    """★貸借が合わない仕訳を通さないこと。ここが本体。"""
    broken = BALANCED.replace("-1000 JPY", "-999 JPY")
    result = bean_check(_write(tmp_path, broken))
    assert not result.ok
    assert result.lines


def test_undeclared_account_fails(tmp_path):
    """勘定科目の打ち間違いを黙って通さない。"""
    typo = BALANCED.replace(
        "Expenses:Personal:Food:Groceries   1000", "Expenses:Personal:Typo   1000"
    )
    assert not bean_check(_write(tmp_path, typo)).ok


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        bean_check(tmp_path / "nope.beancount")


def test_missing_tool_is_not_silently_ok(monkeypatch, tmp_path):
    """検査していないのに通ったように見えるのが一番まずい。"""
    monkeypatch.setattr("shiwake.ledger.check.shutil.which", lambda _: None)
    with pytest.raises(BeanCheckMissingError):
        bean_check(_write(tmp_path, BALANCED))
