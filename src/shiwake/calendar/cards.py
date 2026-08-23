"""rules/accounts.yaml からカードの締め・引落を読む（第4部 §4.1）。"""

from __future__ import annotations

from pathlib import Path

import yaml

from .build import CardSchedule


def load_cards(path: Path | None) -> tuple[list[CardSchedule], list[str]]:
    """カードの一覧と、予定を組めなかった理由。

    ★締め日や引落日が無いカードを既定値で補わない。
      予定日がまるごとズレ、しかも**元帳の貸借は合ったまま**なので
      検算では気づけない。分からないものは予定に出さず、理由を返す。
    """
    if not path or not path.is_file():
        return [], []

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cards: list[CardSchedule] = []
    problems: list[str] = []

    for entry in data.get("cards") or []:
        card_id = str(entry.get("id") or "?")
        missing = [
            key
            for key in ("liability_account", "debit_account", "closing_day", "debit_day")
            if entry.get(key) in (None, "")
        ]
        if missing:
            problems.append(f"{card_id}: {', '.join(missing)} が未設定なので、引落予定を出せません")
            continue

        cards.append(
            CardSchedule(
                card_id=card_id,
                name=str(entry.get("name") or card_id),
                liability_account=str(entry["liability_account"]),
                debit_account=str(entry["debit_account"]),
                closing_day=int(entry["closing_day"]),
                debit_day=int(entry["debit_day"]),
                debit_month_offset=int(entry.get("debit_month_offset", 1)),
                business_day_rule=str(entry.get("business_day_rule") or "next"),
                verified=bool(entry.get("verified_on")),
            )
        )
    return cards, problems
