"""決算書マッピングの網羅性（第2部 §7.2）。

★事業の費目を1つ増やして、決算書への対応づけを忘れると、
  その費目は P/L から**黙って落ちる**。金額が減っても合計は合うので、
  目視では気づけない。ここで機械的に止める。

逆向き（マッピングにあるのに元帳に無い科目）は正常なので、
情報として出すだけにする。開業直後は多くの費目が空になる。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from shiwake.scopes import matches

#: 決算書の表（この節の下に「決算書の科目名: [Beancount の科目]」が並ぶ）
STATEMENT_SECTIONS = ("損益計算書", "貸借対照表")

#: 決算書には出ないが、申告の集計に使う節
EXTRA_SECTIONS = ("申告用",)


@dataclass(frozen=True, order=True)
class MappingIssue:
    severity: Literal["error", "warning"]
    account: str
    message: str

    def format(self) -> str:
        mark = "ERROR  " if self.severity == "error" else "WARNING"
        return f"{mark}  [mapping] {self.account}: {self.message}"


def load_mapping(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _mapped_patterns(mapping: dict) -> list[tuple[str, str]]:
    """(パターン, 決算書の科目名) の一覧。"""
    out: list[tuple[str, str]] = []
    for section in (*STATEMENT_SECTIONS, *EXTRA_SECTIONS):
        for line_name, patterns in (mapping.get(section) or {}).items():
            for pattern in patterns or []:
                out.append((pattern, f"{section}/{line_name}"))
    return out


def check_mapping_coverage(
    accounts: Iterable[str],
    mapping: dict,
    require: str = "Expenses:Business:*",
) -> list[MappingIssue]:
    """元帳の科目が決算書のどこかに対応づいているかを見る。"""
    patterns = _mapped_patterns(mapping)
    excluded = mapping.get("除外") or []
    issues: list[MappingIssue] = []

    for account in sorted(set(accounts)):
        if not matches(require, account):
            continue
        if any(matches(p, account) for p in excluded):
            continue
        hits = [line for pattern, line in patterns if matches(pattern, account)]
        if not hits:
            issues.append(
                MappingIssue(
                    "error",
                    account,
                    "決算書のどの科目にも対応づいていません。"
                    "このままだと損益計算書から黙って落ちます。"
                    "rules/aoiro_mapping.yaml に追加してください",
                )
            )
        elif len(set(hits)) > 1:
            issues.append(
                MappingIssue(
                    "error",
                    account,
                    f"決算書の複数の科目に対応づいています（{', '.join(sorted(set(hits)))}）。"
                    "二重計上になります",
                )
            )
    return sorted(issues)
