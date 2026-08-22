"""名前ベースの検査（第13部 §6.1 第1層）。

自分・取引先・勤務先・銀行・住所などの固有名詞を、
**マシンから出る前に** 止めるための層。

リストそのものが個人情報なので、公開リポジトリには置かない。
非公開リポジトリか ~/.config/shiwake/denylist.txt から読む。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from pathlib import Path

#: これより短い語は誤爆するだけなので無視する
MIN_TERM_LENGTH = 2

DEFAULT_LOCATIONS = (
    Path.home() / ".config" / "shiwake" / "denylist.txt",
    Path("config/denylist.txt"),
)


def _normalize(text: str) -> str:
    """全角/半角と大文字/小文字の揺れを吸収する。"""
    return unicodedata.normalize("NFKC", text).casefold()


class Denylist:
    """固有名詞の一覧。中身は決して出力しない。"""

    def __init__(self, terms: Iterable[str]) -> None:
        seen: dict[str, str] = {}
        for raw in terms:
            term = raw.strip()
            if not term or term.startswith("#"):
                continue
            if len(term) < MIN_TERM_LENGTH:
                continue
            seen.setdefault(_normalize(term), term)
        self._terms = seen

    def __len__(self) -> int:
        return len(self._terms)

    def __bool__(self) -> bool:
        return bool(self._terms)

    @classmethod
    def from_file(cls, path: Path) -> Denylist:
        return cls(path.read_text(encoding="utf-8").splitlines())

    @classmethod
    def discover(cls, extra: Path | None = None) -> Denylist:
        """既定の置き場を順に探して読み込む。見つからなければ空。"""
        terms: list[str] = []
        candidates = list(DEFAULT_LOCATIONS)
        if extra is not None:
            candidates.insert(0, extra)
        for path in candidates:
            if path.is_file():
                terms.extend(path.read_text(encoding="utf-8").splitlines())
        return cls(terms)

    def find(self, text: str) -> list[str]:
        """本文に含まれる語を返す。返るのは正規化済みの語であり、出力してはいけない。"""
        if not self._terms:
            return []
        haystack = _normalize(text)
        return [original for norm, original in self._terms.items() if norm in haystack]
