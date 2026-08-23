"""支払カレンダー（第4部 §4）。

★Phase 10 の受け入れ条件:
  「土日に当たる引落が翌営業日に調整されて表示され、
    残高がマイナスになる日が事前にアラートとして出る」
"""

from __future__ import annotations

from datetime import date

from shiwake.calendar import load_business_days
from shiwake.calendar.build import (
    CardSchedule,
    Event,
    balance_alerts,
    card_debit_events,
    confirmed_balances,
    forecast_balances,
    match_settled,
    recurring_events,
)
from shiwake.calendar.recurring import Recurrence, RecurringItem
from shiwake.web.build_data import LedgerPosting

BD = load_business_days(None)
CARD = CardSchedule(
    card_id="card_a",
    name="サンプルカード",
    liability_account="Liabilities:Personal:CreditCard:A",
    debit_account="Assets:Personal:Bank:A",
    closing_day=15,
    debit_day=10,
    debit_month_offset=1,
    verified=True,
)


def use(day, amount, account="Liabilities:Personal:CreditCard:A"):
    """カード利用（負債は貸方なので負の額）。"""
    return LedgerPosting(
        date=day, payee="", narration="", account=account, amount=-amount, txn_id=f"t{day}"
    )


# ── カードの引落予定 ────────────────────────────────────


def test_uses_in_one_period_become_one_debit():
    """★1件ずつ並べない。締め期間でまとめて1回の引落にする。"""
    postings = [use(date(2026, 7, 20), 1000), use(date(2026, 8, 1), 2000)]
    events = card_debit_events(postings, [CARD], BD, date(2026, 8, 20), date(2027, 8, 31))
    assert len(events) == 1
    assert events[0].amount == 3000
    assert events[0].date == date(2026, 9, 10)


def test_the_period_boundary_splits_debits():
    """15日締め。16日の利用は翌月の請求になる。"""
    postings = [use(date(2026, 7, 15), 1000), use(date(2026, 7, 16), 2000)]
    events = sorted(
        card_debit_events(postings, [CARD], BD, date(2026, 8, 20), date(2027, 8, 31)),
        key=lambda e: e.date,
    )
    assert [e.date for e in events] == [date(2026, 8, 10), date(2026, 9, 10)]
    assert [e.amount for e in events] == [1000, 2000]


def test_debit_on_a_weekend_moves_to_the_next_business_day():
    """★受け入れ条件そのもの。2027-01-10 は日曜。"""
    card = CardSchedule(**{**CARD.__dict__, "card_id": "c2"})
    postings = [use(date(2026, 12, 10), 5000)]
    events = card_debit_events(postings, [card], BD, date(2026, 12, 20), date(2027, 12, 31))
    ev = events[0]
    assert ev.scheduled_date == date(2027, 1, 10)  # 日
    assert ev.date == date(2027, 1, 12)  # 1/11 は成人の日なので、その翌日
    assert ev.adjusted is True
    assert "翌営業日" in ev.adjust_reason


def test_amount_is_estimated_until_the_period_closes():
    """★締め日前は増える。確定したように見せない（第3部 §11）。"""
    postings = [use(date(2026, 8, 20), 1000)]
    events = card_debit_events(postings, [CARD], BD, date(2026, 8, 23), date(2027, 8, 31))
    assert events[0].amount_type == "estimated"


def test_amount_is_fixed_after_the_period_closes():
    postings = [use(date(2026, 7, 20), 1000)]
    events = card_debit_events(postings, [CARD], BD, date(2026, 8, 23), date(2027, 8, 31))
    assert events[0].amount_type == "fixed"


def test_unverified_card_says_so():
    """締め日が未確認なら、予定日も未確認である。黙って出さない。"""
    card = CardSchedule(**{**CARD.__dict__, "verified": False})
    events = card_debit_events(
        [use(date(2026, 7, 20), 1000)], [card], BD, date(2026, 8, 23), date(2027, 8, 31)
    )
    assert events[0].note


def test_settled_period_is_not_shown_again():
    """引落済みで相殺されている期間は予定に出さない。"""
    postings = [
        use(date(2026, 7, 20), 1000),
        LedgerPosting(date(2026, 8, 10), "", "", "Liabilities:Personal:CreditCard:A", 1000),
    ]
    events = card_debit_events(postings, [CARD], BD, date(2026, 8, 23), date(2027, 8, 31))
    assert events == []


# ── 残高予測 ────────────────────────────────────────────


def _bank(day, amount):
    return LedgerPosting(day, "", "", "Assets:Personal:Bank:A", amount)


def test_no_opening_balance_means_no_forecast():
    """★起点が無いのに 0 から予測しない。全部の残高が嘘になる。"""
    out = forecast_balances([], {}, ["Assets:Personal:Bank:A"], date(2026, 9, 1), False)
    assert out[0].points == []
    assert "期首残高" in out[0].unavailable


def test_forecast_runs_the_balance_down():
    events = [
        Event(
            "e1",
            date(2026, 9, 10),
            date(2026, 9, 10),
            "card_debit",
            "out",
            30000,
            "fixed",
            "Assets:Personal:Bank:A",
            "カード",
        ),
    ]
    out = forecast_balances(
        events,
        {"Assets:Personal:Bank:A": 50000},
        ["Assets:Personal:Bank:A"],
        date(2026, 9, 1),
        True,
    )
    assert [p["balance"] for p in out[0].points] == [50000, 20000]


def test_a_shortfall_is_flagged_before_it_happens():
    """★受け入れ条件そのもの。"""
    events = [
        Event(
            "e1",
            date(2026, 9, 10),
            date(2026, 9, 10),
            "card_debit",
            "out",
            80000,
            "fixed",
            "Assets:Personal:Bank:A",
            "カード",
        ),
    ]
    out = forecast_balances(
        events,
        {"Assets:Personal:Bank:A": 50000},
        ["Assets:Personal:Bank:A"],
        date(2026, 9, 1),
        True,
    )
    alerts = balance_alerts(out)
    assert alerts[0]["severity"] == "error"
    assert alerts[0]["date"] == "2026-09-10"
    assert alerts[0]["balance"] == -30000


def test_estimated_events_still_raise_the_alarm():
    """★見込みでも黙らない。落ちる前に気づくための機能なので。"""
    events = [
        Event(
            "e1",
            date(2026, 9, 10),
            date(2026, 9, 10),
            "recurring",
            "out",
            80000,
            "estimated",
            "Assets:Personal:Bank:A",
            "家賃",
        ),
    ]
    out = forecast_balances(
        events,
        {"Assets:Personal:Bank:A": 50000},
        ["Assets:Personal:Bank:A"],
        date(2026, 9, 1),
        True,
    )
    alerts = balance_alerts(out)
    assert alerts and alerts[0]["confirmed"] is False


def test_unknown_amount_does_not_move_the_balance():
    """金額不明の予定で残高を勝手に減らさない。確かさだけ落とす。"""
    events = [
        Event(
            "e1",
            date(2026, 9, 10),
            date(2026, 9, 10),
            "recurring",
            "out",
            None,
            "estimated",
            "Assets:Personal:Bank:A",
            "ガス代",
        ),
    ]
    out = forecast_balances(
        events,
        {"Assets:Personal:Bank:A": 50000},
        ["Assets:Personal:Bank:A"],
        date(2026, 9, 1),
        True,
    )
    assert [p["balance"] for p in out[0].points] == [50000]


def test_confirmed_balances_stop_at_the_cutoff():
    postings = [_bank(date(2026, 8, 1), 10000), _bank(date(2026, 9, 5), -3000)]
    assert confirmed_balances(postings, date(2026, 8, 31)) == {"Assets:Personal:Bank:A": 10000}


# ── 実績との突合 ────────────────────────────────────────


def test_matching_actual_marks_the_event_settled():
    ev = Event(
        "e1",
        date(2026, 9, 10),
        date(2026, 9, 10),
        "card_debit",
        "out",
        30000,
        "fixed",
        "Assets:Personal:Bank:A",
        "カード",
    )
    match_settled([ev], [_bank(date(2026, 9, 10), -30000)])
    assert ev.settled is True
    assert ev.settled_date == date(2026, 9, 10)


def test_a_few_days_apart_still_matches():
    ev = Event(
        "e1",
        date(2026, 9, 10),
        date(2026, 9, 10),
        "card_debit",
        "out",
        30000,
        "fixed",
        "Assets:Personal:Bank:A",
        "カード",
    )
    match_settled([ev], [_bank(date(2026, 9, 13), -30000)])
    assert ev.settled is True


def test_an_event_that_never_happened_stays_unsettled():
    """★落ちなかったものを自動で消さない。実際に1回落ちていなかった。"""
    ev = Event(
        "e1",
        date(2026, 8, 10),
        date(2026, 8, 10),
        "card_debit",
        "out",
        53516,
        "fixed",
        "Assets:Personal:Bank:A",
        "カード",
    )
    match_settled([ev], [_bank(date(2026, 8, 10), -1000)])
    assert ev.settled is False


def test_one_actual_settles_only_one_event():
    """★同じ入出金を2つの予定に割り当てない（二重計上と同じ穴）。"""
    events = [
        Event(
            f"e{i}",
            date(2026, 9, 10),
            date(2026, 9, 10),
            "card_debit",
            "out",
            30000,
            "fixed",
            "Assets:Personal:Bank:A",
            "カード",
        )
        for i in range(2)
    ]
    match_settled(events, [_bank(date(2026, 9, 10), -30000)])
    assert [e.settled for e in events] == [True, False]


# ── 定期の予定 ──────────────────────────────────────────


def test_recurring_rent_moves_to_the_previous_business_day():
    item = RecurringItem(
        id="rent",
        name="家賃",
        direction="out",
        kind="transfer",
        amount=45000,
        amount_type="fixed",
        recurrence=Recurrence(frequency="monthly", day=27, business_day_rule="previous"),
        account="Assets:Personal:Bank:A",
    )
    events = recurring_events([item], BD, date(2026, 9, 1), date(2026, 9, 30))
    assert events[0].scheduled_date == date(2026, 9, 27)  # 日
    assert events[0].date == date(2026, 9, 25)  # 金
    assert "前営業日" in events[0].adjust_reason
