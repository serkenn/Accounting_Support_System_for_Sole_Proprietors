"""検出結果の型。

★ 検出器そのものが漏洩経路にならないようにする。
   秘密を見つけたことを報告するときに、その秘密を出力してはいけない
   （ログ・CI の出力・Issue の貼り付けに残る）。
   したがって Finding は原文の断片を持たず、マスク済みの表現だけを持つ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


def mask(value: str) -> str:
    """秘密をマスクした表現を返す。原文が復元できないこと。"""
    length = len(value)
    if length >= 10:
        return f"{value[:2]}…{value[-2:]}（{length}文字）"
    return f"<{length}文字>"


def mask_fully(value: str) -> str:
    """一切の断片も出さない。デノイリスト（名前）に使う。"""
    return f"<{len(value)}文字>"


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    rule: str
    severity: Severity
    message: str
    excerpt: str

    def format(self) -> str:
        mark = "ERROR  " if self.severity == "error" else "WARNING"
        return f"{mark} {self.path}:{self.line}  [{self.rule}] {self.message} — {self.excerpt}"
