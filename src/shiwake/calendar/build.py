"""支払カレンダーの生成（第4部 §4）。

★カレンダーに出るのは、**すでに元帳に載っている債権債務が「いつ現金になるか」**が中心。
  それに未計上の定期支払い（家賃・サブスク・税金）を足したものが資金繰り表になる。

  記帳日と支払日は別物である（第4部 §0）。
    カードで買った → 元帳は利用日、カレンダーは引落日
  ここを混ぜると、発生主義の元帳が壊れるか、資金繰りが1か月ずれるかのどちらかになる。

★予定を Beancount に書かない。元帳は実績だけを持つ。
  カレンダーは元帳から**読んで**予定を組み立てる、一方向の関係にする。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from shiwake.web.build_data import LedgerPosting

from .business_days import BusinessDays
from .recurring import RecurringItem, occurrences

#: 予定を出す既定の期間（D17）。ローンの完済予定まで見えるように長めに取る。
DEFAULT_HORIZON_MONTHS = 12


@dataclass(frozen=True)
class CardSchedule:
    """カードの締めと引落（rules/accounts.yaml から）。"""

    card_id: str
    name: str
    liability_account: str
    debit_account: str
    closing_day: int
    debit_day: int
    debit_month_offset: int
    business_day_rule: str = "next"
    verified: bool = False


@dataclass
class Event:
    id: str
    date: date
    scheduled_date: date
    kind: str
    direction: str
    amount: int | None
    amount_type: str
    account: str | None
    counterparty: str | None
    source: dict[str, Any] = field(default_factory=dict)
    adjust_reason: str | None = None
    settled: bool = False
    settled_date: date | None = None
    note: str | None = None

    @property
    def adjusted(self) -> bool:
        return self.date != self.scheduled_date

    def signed(self) -> int | None:
        if self.amount is None:
            return None
        return self.amount if self.direction == "in" else -self.amount

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "scheduled_date": self.scheduled_date.isoformat(),
            "adjusted": self.adjusted,
            "adjust_reason": self.adjust_reason,
            "kind": self.kind,
            "direction": self.direction,
            "amount": self.amount,
            "amount_type": self.amount_type,
            "account": self.account,
            "counterparty": self.counterparty,
            "source": self.source,
            "settled": self.settled,
            "settled_date": self.settled_date.isoformat() if self.settled_date else None,
            "note": self.note,
        }


def _period_of(day: date, closing_day: int) -> tuple[date, date]:
    """その利用日が属する締め期間（開始日, 締め日）。"""
    if day.day <= closing_day:
        end_year, end_month = day.year, day.month
    else:
        end_month = day.month + 1
        end_year = day.year + (1 if end_month > 12 else 0)
        end_month = 1 if end_month > 12 else end_month
    end = date(end_year, end_month, min(closing_day, _days_in(end_year, end_month)))
    start_month = end.month - 1
    start_year = end.year - (1 if start_month < 1 else 0)
    start_month = 12 if start_month < 1 else start_month
    start = date(start_year, start_month, min(closing_day, _days_in(start_year, start_month)))
    return start + timedelta(days=1), end


def _days_in(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def _debit_date(closing: date, card: CardSchedule) -> date:
    month = closing.month + card.debit_month_offset
    year = closing.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, min(card.debit_day, _days_in(year, month)))


def card_debit_events(
    postings: list[LedgerPosting],
    cards: list[CardSchedule],
    business_days: BusinessDays,
    today: date,
    horizon_end: date,
) -> list[Event]:
    """カードの引落予定を、元帳の負債から組み立てる（第4部 §4.1）。

    ★推測で作らない。元帳に載っている利用分だけを締め期間ごとにまとめる。
      「毎月だいたいこのくらい」という予定は作らない。
    """
    events: list[Event] = []
    for card in cards:
        # 締め期間ごとの利用額。負債は貸方なので符号を反転して集める。
        by_period: dict[date, int] = defaultdict(int)
        for p in postings:
            if p.account != card.liability_account:
                continue
            _start, closing = _period_of(p.date, card.closing_day)
            by_period[closing] += -p.amount

        for closing, amount in sorted(by_period.items()):
            if amount <= 0:
                # 引落済みで相殺されている期間。予定には出さない。
                continue
            scheduled = _debit_date(closing, card)
            if scheduled > horizon_end:
                continue
            adj = business_days.adjust(scheduled, card.business_day_rule)
            events.append(
                Event(
                    id=f"ev_card_{card.card_id}_{closing:%Y%m%d}",
                    date=adj.date,
                    scheduled_date=adj.scheduled_date,
                    kind="card_debit",
                    direction="out",
                    amount=amount,
                    # ★締め日を過ぎていれば額は確定。まだなら増える見込み。
                    amount_type="fixed" if closing <= today else "estimated",
                    account=card.debit_account,
                    counterparty=card.name,
                    source={
                        "type": "card",
                        "card_id": card.card_id,
                        "closing_date": closing.isoformat(),
                    },
                    adjust_reason=adj.reason,
                    note=None if card.verified else "締め日・引落日を明細で確認していません",
                )
            )
    return events


def recurring_events(
    items: list[RecurringItem],
    business_days: BusinessDays,
    start: date,
    end: date,
) -> list[Event]:
    events: list[Event] = []
    for item in items:
        for when in occurrences(item, start, end):
            adj = business_days.adjust(when, item.recurrence.business_day_rule)
            events.append(
                Event(
                    id=f"ev_rec_{item.id}_{when:%Y%m%d}",
                    date=adj.date,
                    scheduled_date=adj.scheduled_date,
                    kind="recurring",
                    direction=item.direction,
                    amount=item.amount,
                    amount_type=item.amount_type,
                    account=item.account,
                    counterparty=item.counterparty or item.name,
                    source={"type": "recurring", "item_id": item.id},
                    adjust_reason=adj.reason,
                    note=item.note,
                )
            )
    return events


@dataclass
class Forecast:
    """口座ごとの残高の見通し。

    ★起点は**最新の確定残高**。それが無ければ予測しない。
      起点を 0 と置くと、全部の残高がまるごと嘘になる。
      「分からない」と出すほうが、間違った数字より役に立つ。
    """

    account: str
    points: list[dict] = field(default_factory=list)
    #: 予測できない理由。あれば points は空になる。
    unavailable: str | None = None


def confirmed_balances(postings: list[LedgerPosting], as_of: date) -> dict[str, int]:
    """指定日までの実績から出した各口座の残高。"""
    out: dict[str, int] = defaultdict(int)
    for p in postings:
        if p.date <= as_of:
            out[p.account] += p.amount
    return dict(out)


def forecast_balances(
    events: list[Event],
    opening: dict[str, int],
    accounts: list[str],
    start: date,
    has_opening_balance: bool,
) -> list[Forecast]:
    out: list[Forecast] = []
    for account in accounts:
        if not has_opening_balance:
            out.append(
                Forecast(
                    account=account,
                    unavailable=(
                        "期首残高が入っていないため、残高を予測できません。"
                        "ledger/manual/opening.beancount に実際の残高を入れてください"
                    ),
                )
            )
            continue

        running = opening.get(account, 0)
        points = [{"date": start.isoformat(), "balance": running, "confirmed": True}]
        estimated = False
        for ev in sorted(events, key=lambda e: e.date):
            if ev.account != account or ev.date < start:
                continue
            delta = ev.signed()
            if delta is None:
                # 金額が分からない予定。残高を動かさず、確かさだけ落とす。
                estimated = True
                continue
            running += delta
            estimated = estimated or ev.amount_type == "estimated"
            points.append(
                {
                    "date": ev.date.isoformat(),
                    "balance": running,
                    "confirmed": not estimated,
                }
            )
        out.append(Forecast(account=account, points=points))
    return out


def balance_alerts(forecasts: list[Forecast], threshold: int = 0) -> list[dict]:
    """残高が閾値を下回る日（第4部 §4.3）。

    ★見込みを含む予測でも黙らない。落ちる前に気づくための機能なので、
      「見込みだから」と伏せると存在意義が無くなる。確かさは併記する。
    """
    alerts: list[dict] = []
    for forecast in forecasts:
        for point in forecast.points:
            if point["balance"] < threshold:
                alerts.append(
                    {
                        "date": point["date"],
                        "account": forecast.account,
                        "balance": point["balance"],
                        "severity": "error" if point["balance"] < 0 else "warning",
                        "confirmed": point["confirmed"],
                        "message": (
                            "残高が不足する見込みです"
                            if point["balance"] < 0
                            else "残高が少なくなる見込みです"
                        ),
                    }
                )
                break  # 口座ごとに最初の1件で足りる。同じ話を並べない
    return alerts


def match_settled(events: list[Event], postings: list[LedgerPosting]) -> None:
    """予定と実績を突き合わせる（第4部 §4.4）。

    一致条件: 金額一致 かつ 日付差 5日以内 かつ 口座一致。

    ★予定日を過ぎても未決済のものを自動で消さない。「未着」として残す。
      消すと、落ちなかったことに気づけない。実際にカードの引落が
      1回落ちていなかった。
    """
    used: set[int] = set()
    for ev in sorted(events, key=lambda e: e.date):
        if ev.amount is None:
            continue
        want = ev.signed()
        for i, p in enumerate(postings):
            if i in used or p.account != ev.account or p.amount != want:
                continue
            if abs((p.date - ev.date).days) > 5:
                continue
            ev.settled = True
            ev.settled_date = p.date
            used.add(i)
            break
