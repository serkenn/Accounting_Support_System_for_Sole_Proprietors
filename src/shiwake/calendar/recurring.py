"""定期的な予定（第4部 §3）。

元帳にまだ載っていない、繰り返し発生する入出金。家賃・公共料金・税金。

★税金と社会保険料をここに入れ忘れると、資金繰りが破綻する代表格になる。
  年に数回しか来ないので、月次の感覚から落ちる。

★金額が「見込み」のものは、必ずそう表示する（第3部 §11）。
  確定額と見込み額を同じ顔で並べると、足りるかどうかの判断を誤る。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import yaml

Direction = Literal["in", "out"]
AmountType = Literal["fixed", "estimated"]


@dataclass(frozen=True)
class Recurrence:
    frequency: Literal["monthly", "yearly"]
    day: int
    months: tuple[int, ...] = ()
    business_day_rule: str | None = None


@dataclass(frozen=True)
class RecurringItem:
    id: str
    name: str
    direction: Direction
    kind: str
    amount: int | None
    amount_type: AmountType
    recurrence: Recurrence
    account: str | None = None
    counterparty: str | None = None
    expected_account: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    note: str | None = None

    def active_on(self, day: date) -> bool:
        if self.starts_on and day < self.starts_on:
            return False
        return not (self.ends_on and day > self.ends_on)


@dataclass
class RecurringSchedule:
    items: list[RecurringItem] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _last_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def occurrences(item: RecurringItem, start: date, end: date) -> list[date]:
    """期間内の発生日（営業日調整**前**）。"""
    out: list[date] = []
    year, month = start.year, start.month
    while date(year, month, 1) <= end:
        if item.recurrence.frequency == "yearly" and month not in item.recurrence.months:
            month, year = (month + 1, year) if month < 12 else (1, year + 1)
            continue
        # ★31日指定の月末。2月に31日は無いので、その月の末日に寄せる。
        #   例外にすると毎年2月に落ちる。
        day = min(item.recurrence.day, _last_day(year, month))
        when = date(year, month, day)
        if start <= when <= end and item.active_on(when):
            out.append(when)
        month, year = (month + 1, year) if month < 12 else (1, year + 1)
    return out


def load_recurring(path: Path | None) -> RecurringSchedule:
    if not path or not path.is_file():
        return RecurringSchedule()

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    schedule = RecurringSchedule()

    for raw in data.get("items") or []:
        item_id = str(raw.get("id") or "?")
        rec = raw.get("recurrence") or {}
        frequency = rec.get("frequency", "monthly")

        if frequency not in ("monthly", "yearly"):
            schedule.problems.append(f"{item_id}: 知らない周期です: {frequency}")
            continue
        if not rec.get("day"):
            schedule.problems.append(f"{item_id}: recurrence.day がありません")
            continue
        if frequency == "yearly" and not rec.get("months"):
            schedule.problems.append(f"{item_id}: 年次なのに months がありません")
            continue

        amount = raw.get("amount")
        amount_type = raw.get("amount_type", "estimated")
        # ★金額が無いものを 0 として扱わない。0円の予定として並ぶと
        #   「その支払いは無い」という意味に読めてしまう。
        if amount is None and amount_type == "fixed":
            schedule.problems.append(
                f"{item_id}: 金額が無いのに amount_type が fixed です。"
                "分からないなら estimated にしてください"
            )
            continue

        schedule.items.append(
            RecurringItem(
                id=item_id,
                name=str(raw.get("name") or item_id),
                direction=raw.get("direction", "out"),
                kind=raw.get("kind", "transfer"),
                amount=amount,
                amount_type=amount_type,
                recurrence=Recurrence(
                    frequency=frequency,
                    day=int(rec["day"]),
                    months=tuple(rec.get("months") or ()),
                    business_day_rule=rec.get("business_day_rule"),
                ),
                account=raw.get("account"),
                counterparty=raw.get("counterparty"),
                expected_account=raw.get("expected_account"),
                starts_on=raw.get("starts_on"),
                ends_on=raw.get("ends_on"),
                note=raw.get("note"),
            )
        )
    return schedule
