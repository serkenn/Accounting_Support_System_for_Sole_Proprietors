"""カレンダーの JSON（第4部 §4.2）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from .build import Event, Forecast

SCHEMA_VERSION = 1


def calendar_json(
    events: list[Event],
    forecasts: list[Forecast],
    alerts: list[dict],
    horizon: tuple[date, date],
    generated_at: str,
    commit: str = "",
    problems: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "commit": commit,
        "horizon": {"from": horizon[0].isoformat(), "to": horizon[1].isoformat()},
        "events": [e.as_dict() for e in sorted(events, key=lambda e: (e.date, e.id))],
        "balance_forecast": {
            f.account: {"points": f.points, "unavailable": f.unavailable} for f in forecasts
        },
        "alerts": alerts,
        # ★予定を出せなかったものを黙って落とさない。
        #   「予定が無い」と「予定を出せない」は意味がまるで違う。
        "problems": problems or [],
    }
