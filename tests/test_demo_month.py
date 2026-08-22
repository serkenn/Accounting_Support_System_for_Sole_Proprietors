"""合成の1か月分を通した受け入れテスト（第1部 Phase 2）。

**受け入れ条件**: 1か月分（カード明細1通 + 領収書10枚）を投入し、
`bean-check` が通り、**カード払いの合計がカード明細の総額と一致**する
（＝二重計上ゼロ）。

ここが通らなくなったら、システムの中心が壊れている。
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path

import pytest

from shiwake.ledger import bean_check, bean_check_available

DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "demo"
MAIN = DEMO / "main.beancount"
CARD = "Liabilities:Personal:CreditCard:Sample"

pytestmark = pytest.mark.skipif(not bean_check_available(), reason="bean-check が未インストール")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """毎回組み立て直す。生成物をコミットしていても、生成できることを確かめる。"""
    subprocess.run(
        ["python", str(DEMO / "build_demo.py")],
        check=True,
        capture_output=True,
        cwd=DEMO.parents[1],
    )
    return MAIN


def query(sql: str) -> list[dict]:
    out = subprocess.run(
        ["bean-query", "-f", "csv", str(MAIN), sql], capture_output=True, text=True, check=True
    ).stdout
    return list(csv.DictReader(io.StringIO(out)))


def scalar(sql: str) -> int:
    rows = query(sql)
    return int((rows[0].get("n") or "0").strip() or 0) if rows else 0


def statement() -> dict:
    path = next((DEMO / "documents").glob("*samplecard*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


# ── 受け入れ条件 ────────────────────────────────────────


def test_ledger_passes_bean_check(built):
    assert bean_check(built).ok


def test_card_charges_equal_the_statement_total(built):
    """★これが本体。ここが合わなければ二重計上か取り込み漏れ。"""
    total = statement()["statement_total"]
    charged = -scalar(f"SELECT sum(number) AS n WHERE account = '{CARD}' AND date <= 2026-07-31")
    assert charged == total


def test_remaining_balance_is_only_the_pending_item(built):
    """引落後に残るのは、明細がまだ届いていない分だけ。"""
    assert -scalar(f"SELECT sum(number) AS n WHERE account = '{CARD}'") == 950


def test_bridge_invariant_holds(built):
    """★持分 + 資本 = 0（Phase 12 の不変条件）。"""
    assert scalar("SELECT sum(number) AS n WHERE account ~ 'BusinessInterest|Equity:Owner'") == 0


def test_no_salary_or_personal_assets_in_business_scope(built):
    rows = query("SELECT account WHERE account ~ ':Business:' GROUP BY account")
    accounts = {r["account"] for r in rows}
    assert accounts
    assert not any("Employment" in a or ":Personal:" in a for a in accounts)


# ── 突合の質 ────────────────────────────────────────────


def test_same_merchant_same_day_same_amount_is_not_auto_linked():
    """★同店同日同額は自動確定しない。人が選んだものだけがリンクされる。"""
    links = json.loads((DEMO / "links" / "2026-07.json").read_text(encoding="utf-8"))["links"]
    stmt_id = statement()["doc_id"]
    # L005 と L006 は同額同日。片方だけがリンクされていること
    linked_lines = set(links.values())
    assert f"{stmt_id}:L005" in linked_lines
    assert f"{stmt_id}:L006" not in linked_lines


def test_every_receipt_appears_in_the_ledger(built):
    """★領収書が黙って消えていないこと。

    分類できないものはエラーで止まる作りなので、生成が通った時点で
    全部の領収書が仕訳になっているはず。それを元帳側から数えて確かめる。
    """
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in (DEMO / "documents").glob("*.json")]
    receipt_ids = {d["doc_id"] for d in docs if d["type"] == "receipt"}

    ledger_text = (DEMO / "ledger" / "2026-07.beancount").read_text(encoding="utf-8")
    missing = sorted(doc_id for doc_id in receipt_ids if doc_id not in ledger_text)
    assert not missing, f"元帳に現れない領収書: {missing}"


def test_fixtures_are_marked_synthetic():
    """第13部 §5 — 公開側のフィクスチャは合成データのみ。"""
    for path in (DEMO / "rules").glob("*.yaml"):
        assert "SYNTHETIC" in path.read_text(encoding="utf-8")
    assert "SYNTHETIC" in (DEMO / "ledger" / "2026-07.beancount").read_text(encoding="utf-8")
