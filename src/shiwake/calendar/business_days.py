"""営業日の調整（第4部 §1）。

★ここを曖昧にすると全部狂う。予定日が金融機関の休業日なら移動するが、
  **どちらへ動くかは契約ごとに違う**。

    引落  たいてい翌営業日。ただし規約次第で前営業日のこともある
    家賃  前営業日までに振り込むのが普通

  既定に寄りかからず、契約ごとに指定できるようにする（D19）。

★調整した事実を捨てない。画面には調整後を主に出すが、調整前も併記する。
  「27日に落ちるはず」と思っている本人と、画面の日付が食い違うため。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import yaml

Rule = Literal["next", "previous", "none"]

#: 曜日の記号。YAML に 0/1 の数字を書かせない（読み手が数えることになる）。
WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

#: 祝日ではないが金融機関が休む日（月-日）。
DEFAULT_EXTRA_CLOSURES = ("12-31", "01-01", "01-02", "01-03")


@dataclass(frozen=True)
class Adjustment:
    """調整の結果。**調整前の日付を必ず持ち歩く。**"""

    date: date
    scheduled_date: date
    reason: str | None = None

    @property
    def adjusted(self) -> bool:
        return self.date != self.scheduled_date


@dataclass
class BusinessDays:
    weekend: frozenset[int]
    extra_closures: frozenset[str]
    default_rule: Rule = "next"
    #: 祝日を見るかどうか。ライブラリが無い環境でも動くようにする。
    use_holidays: bool = True

    def _holiday_name(self, day: date) -> str | None:
        if not self.use_holidays:
            return None
        try:
            import jpholiday
        except ImportError:  # pragma: no cover - 依存を入れていない環境
            return None
        name = jpholiday.is_holiday_name(day)
        return str(name) if name else None

    def closed_reason(self, day: date) -> str | None:
        """休業日ならその理由。営業日なら None。"""
        if day.weekday() in self.weekend:
            return f"{'月火水木金土日'[day.weekday()]}曜のため"
        # ★祝日を先に見る。「元日のため」と出したいので、
        #   extra_closures の一般的な文言で上書きさせない。
        name = self._holiday_name(day)
        if name:
            return f"{name}のため"
        if day.strftime("%m-%d") in self.extra_closures:
            return "金融機関の休業日のため"
        return None

    def is_business_day(self, day: date) -> bool:
        return self.closed_reason(day) is None

    def adjust(self, day: date, rule: Rule | None = None) -> Adjustment:
        """休業日なら動かす。動かした理由を残す。"""
        rule = rule or self.default_rule
        reason = self.closed_reason(day)
        if reason is None or rule == "none":
            return Adjustment(date=day, scheduled_date=day)

        step = timedelta(days=1 if rule == "next" else -1)
        moved = day
        # ★年末年始は連続で休む。1日ずらすだけでは足りない。
        #   無限に回らないよう上限を置く（連休は現実的に10日を超えない）。
        for _ in range(15):
            moved += step
            if self.is_business_day(moved):
                where = "翌営業日" if rule == "next" else "前営業日"
                return Adjustment(moved, day, f"{day:%-m/%-d}は{reason}{where}")
        raise ValueError(f"{day} から営業日が見つかりません。休業日の設定を確かめてください")


def load_business_days(path: Path | None = None) -> BusinessDays:
    data = {}
    if path and path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    weekend = frozenset(WEEKDAYS[str(code).upper()] for code in data.get("weekend", ["SA", "SU"]))
    return BusinessDays(
        weekend=weekend,
        extra_closures=frozenset(
            str(d) for d in data.get("extra_closures", DEFAULT_EXTRA_CLOSURES)
        ),
        default_rule=data.get("default_rule", "next"),
        use_holidays=bool(data.get("holiday_source", "jpholiday")),
    )
