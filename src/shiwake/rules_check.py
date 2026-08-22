"""口座・カードのマスタの検査（第1部 D5 / 第4部 §1）。

★調べただけで確かめていない値を、黙って信用しない。

  締め日と引落日は資金繰りの予定日を決める。ここが違うと
  カレンダーがまるごとズレるが、**ズレても元帳の貸借は合う**ので
  検算では気づけない。だから値そのものの出どころを検査する。

確かめる一番確実な方法は、手元の利用明細を1枚見ること。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

Severity = Literal["error", "warning"]

#: 下4桁として保存してよい形
LAST4 = 4


@dataclass(frozen=True)
class RuleIssue:
    severity: Severity
    target: str
    message: str

    def format(self) -> str:
        mark = "ERROR  " if self.severity == "error" else "WARNING"
        return f"{mark}  [rules] {self.target}: {self.message}"


def _last4_ok(value: object) -> bool:
    return isinstance(value, str) and len(value) == LAST4 and value.isdigit()


def check_accounts(path: Path) -> list[RuleIssue]:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    issues: list[RuleIssue] = []

    for kind, entries in (("banks", data.get("banks")), ("cards", data.get("cards"))):
        for entry in entries or []:
            target = f"{kind}/{entry.get('id', '?')}"

            if entry.get("namespace") not in ("business", "personal", "mixed"):
                issues.append(
                    RuleIssue(
                        "error", target, "namespace は business / personal / mixed のいずれか"
                    )
                )

            for field in ("account_no_last4", "card_last4"):
                value = entry.get(field)
                if value is not None and not _last4_ok(value):
                    issues.append(
                        RuleIssue(
                            "error",
                            target,
                            f"{field} は下4桁のみ。それより長い番号を保存しない（第1部 §9.1）",
                        )
                    )

            # ★混在なら資産・負債は家計側に置く（Q3 の決定）
            namespace = entry.get("namespace")
            account = entry.get("account") or entry.get("liability_account") or ""
            if namespace == "mixed" and ":Personal:" not in account:
                issues.append(
                    RuleIssue(
                        "error",
                        target,
                        "混在の口座・カードは *:Personal:* に置きます。"
                        "私用と混ざったものは会計上も個人の資産負債であり、"
                        "事業の貸借対照表には載せません",
                    )
                )

            if kind == "cards":
                issues.extend(_check_card_schedule(entry, target))

    return issues


def _check_card_schedule(entry: dict, target: str) -> list[RuleIssue]:
    """★締め日・引落日が確かめられているか。

    ここが違うと資金繰りの予定日がまるごとズレる。
    しかも**ズレても元帳の貸借は合う**ので、検算では気づけない。
    """
    issues: list[RuleIssue] = []
    schedule = ("closing_day", "debit_day")
    missing = [f for f in schedule if entry.get(f) is None]

    if missing:
        issues.append(
            RuleIssue(
                "warning",
                target,
                f"{', '.join(missing)} が未設定です。資金繰りの予定日が出せません",
            )
        )
        return issues

    if not entry.get("verified_on"):
        issues.append(
            RuleIssue(
                "warning",
                target,
                "締め日・引落日を明細で確認していません。"
                "利用明細の「ご利用期間」と「お支払日」を1枚見て、"
                "合っていれば verified_on に日付を入れてください",
            )
        )
    return issues
