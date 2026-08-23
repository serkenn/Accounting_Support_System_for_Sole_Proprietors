"""営業日の調整（第4部 §1）。

★Phase 10 の受け入れ条件のひとつ:
  「土日に当たる引落が翌営業日に調整されて表示される」
"""

from __future__ import annotations

import textwrap
from datetime import date

import pytest

from shiwake.calendar import BusinessDays, load_business_days


@pytest.fixture
def bd():
    return load_business_days(None)


def test_weekday_is_left_alone(bd):
    out = bd.adjust(date(2026, 9, 30))  # 水
    assert out.date == date(2026, 9, 30)
    assert out.adjusted is False
    assert out.reason is None


def test_saturday_debit_moves_to_monday(bd):
    """★受け入れ条件そのもの。"""
    out = bd.adjust(date(2026, 9, 26))  # 土
    assert out.date == date(2026, 9, 28)  # 月
    assert out.adjusted is True
    assert "土曜" in out.reason
    assert "翌営業日" in out.reason


def test_the_original_date_is_never_lost(bd):
    """★調整前を捨てない。本人の頭の中の日付と食い違うため。"""
    out = bd.adjust(date(2026, 9, 26))
    assert out.scheduled_date == date(2026, 9, 26)


def test_rent_moves_backwards(bd):
    """家賃は前営業日までに振り込む。既定に寄りかからない（D19）。"""
    out = bd.adjust(date(2026, 9, 26), "previous")
    assert out.date == date(2026, 9, 25)  # 金
    assert "前営業日" in out.reason


def test_rule_none_leaves_it_on_the_holiday(bd):
    out = bd.adjust(date(2026, 9, 26), "none")
    assert out.date == date(2026, 9, 26)
    assert out.adjusted is False


def test_national_holiday_is_a_closure(bd):
    """1月1日は元日。祝日を見ないと調整が漏れる。"""
    assert bd.is_business_day(date(2026, 1, 1)) is False


def test_new_year_run_is_skipped_entirely(bd):
    """★1日ずらすだけでは足りない。年末年始は連続で休む。"""
    out = bd.adjust(date(2025, 12, 31))
    assert out.date == date(2026, 1, 5)  # 月
    assert bd.is_business_day(out.date)


def test_holiday_reason_names_the_holiday(bd):
    out = bd.adjust(date(2026, 1, 1))
    assert "元日" in out.reason


def test_config_can_change_the_weekend(tmp_path):
    p = tmp_path / "business_days.yaml"
    p.write_text(
        textwrap.dedent(
            """
            weekend: [SU]
            default_rule: previous
            extra_closures: []
            """
        ),
        encoding="utf-8",
    )
    bd = load_business_days(p)
    assert bd.is_business_day(date(2026, 9, 26))  # 土は営業日
    assert bd.adjust(date(2026, 9, 27)).date == date(2026, 9, 26)  # 日→前営業日の土


def test_holidays_can_be_turned_off(tmp_path):
    p = tmp_path / "business_days.yaml"
    p.write_text("holiday_source: null\nextra_closures: []\n", encoding="utf-8")
    bd = load_business_days(p)
    assert bd.is_business_day(date(2026, 1, 1)) is True


def test_impossible_configuration_is_reported_not_looped():
    """全部休みにしたら、黙って回り続けずに止まること。"""
    bd = BusinessDays(weekend=frozenset(range(7)), extra_closures=frozenset())
    with pytest.raises(ValueError, match="営業日"):
        bd.adjust(date(2026, 9, 26))
