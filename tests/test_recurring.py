"""定期的な予定（第4部 §3）。"""

from __future__ import annotations

import textwrap
from datetime import date

from shiwake.calendar.recurring import load_recurring, occurrences


def _load(tmp_path, text):
    p = tmp_path / "recurring.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return load_recurring(p)


RENT = """
    version: 1
    items:
      - id: rent
        name: "家賃"
        direction: out
        kind: transfer
        amount: 45000
        amount_type: fixed
        recurrence: { frequency: monthly, day: 27, business_day_rule: previous }
        starts_on: 2026-04-01
"""


def test_monthly_item_repeats(tmp_path):
    item = _load(tmp_path, RENT).items[0]
    days = occurrences(item, date(2026, 9, 1), date(2026, 11, 30))
    assert days == [date(2026, 9, 27), date(2026, 10, 27), date(2026, 11, 27)]


def test_day_31_falls_back_to_the_end_of_short_months(tmp_path):
    """★2月に31日は無い。例外にすると毎年2月に落ちる。"""
    item = _load(
        tmp_path,
        """
        items:
          - id: x
            name: "月末払い"
            amount: 1000
            amount_type: fixed
            recurrence: { frequency: monthly, day: 31 }
        """,
    ).items[0]
    days = occurrences(item, date(2026, 1, 1), date(2026, 3, 31))
    assert days == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]


def test_yearly_item_only_fires_in_its_months(tmp_path):
    """★住民税は年4回。忘れると資金繰りが破綻する代表格。"""
    item = _load(
        tmp_path,
        """
        items:
          - id: resident_tax
            name: "住民税"
            amount_type: estimated
            recurrence: { frequency: yearly, months: [6, 8, 10, 1], day: 30 }
        """,
    ).items[0]
    days = occurrences(item, date(2026, 1, 1), date(2026, 12, 31))
    assert [d.month for d in days] == [1, 6, 8, 10]


def test_item_before_its_start_is_skipped(tmp_path):
    item = _load(tmp_path, RENT).items[0]
    assert occurrences(item, date(2026, 1, 1), date(2026, 3, 31)) == []


def test_ended_item_stops(tmp_path):
    item = _load(
        tmp_path,
        """
        items:
          - id: x
            amount: 100
            amount_type: fixed
            recurrence: { frequency: monthly, day: 10 }
            ends_on: 2026-10-31
        """,
    ).items[0]
    days = occurrences(item, date(2026, 9, 1), date(2026, 12, 31))
    assert days == [date(2026, 9, 10), date(2026, 10, 10)]


# ── 推測で埋めない ──────────────────────────────────────


def test_missing_amount_cannot_be_called_fixed(tmp_path):
    """★金額が無いものを 0 として並べない。

    0円の予定として出ると「その支払いは無い」という意味に読める。
    """
    schedule = _load(
        tmp_path,
        """
        items:
          - id: gas
            name: "ガス代"
            amount_type: fixed
            recurrence: { frequency: monthly, day: 25 }
        """,
    )
    assert schedule.items == []
    assert any("gas" in p for p in schedule.problems)


def test_estimated_item_without_an_amount_is_kept(tmp_path):
    """見込みなら金額不明でもよい。画面に「見込み」と出す。"""
    schedule = _load(
        tmp_path,
        """
        items:
          - id: gas
            name: "ガス代"
            amount_type: estimated
            recurrence: { frequency: monthly, day: 25 }
        """,
    )
    assert schedule.items[0].amount is None
    assert schedule.items[0].amount_type == "estimated"


def test_unknown_frequency_is_reported(tmp_path):
    schedule = _load(
        tmp_path,
        """
        items:
          - id: x
            amount: 1
            amount_type: fixed
            recurrence: { frequency: fortnightly, day: 1 }
        """,
    )
    assert schedule.items == []
    assert schedule.problems


def test_missing_file_is_empty_not_an_error():
    assert load_recurring(None).items == []
