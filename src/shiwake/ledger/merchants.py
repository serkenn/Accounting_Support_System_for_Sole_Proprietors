"""店名の正規化と一致判定（第1部 §6）。

突合の一致条件は「金額完全一致 かつ 日付差 ≤ 3日 かつ 店名の類似度 ≥ 0.6」。
このうち店名だけが厄介で、実務では表記がまず揃わない。

  カード明細  サンプルストア ワタダ      （カタカナ・支店名が略される）
  領収書      サンプルストア 和多田店    （漢字・正式名）

この2つの文字列の類似度は低い。つまり**類似度だけでは突合できない**。
そこで `rules/merchants.yaml` の別名辞書を主にし、類似度は補助に回す。

辞書は運用で育つ。突合できなかったものを人が結び付けたら、
その対応を辞書に足す。次からは決定的に一致する。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import yaml

#: 店名の末尾によく付く語。比較の邪魔になるので落とす
_NOISE = re.compile(
    r"(株式会社|有限会社|合同会社|\(株\)|\(有\)|㈱|㈲|co\.,?ltd\.?|inc\.?|corp\.?)",
    re.IGNORECASE,
)
_SEPARATORS = re.compile(r"[\s　・･\-ー－/／|｜,，.．]+")


def normalize(name: str) -> str:
    """全角半角・大文字小文字・記号・法人格の揺れを落とす。"""
    text = unicodedata.normalize("NFKC", name).casefold()
    text = _NOISE.sub("", text)
    return _SEPARATORS.sub("", text).strip()


def similarity(a: str, b: str) -> float:
    """正規化したうえでの類似度（0.0–1.0）。"""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # 片方がもう片方を含む（支店名の有無など）は強い一致とみなす
    if na in nb or nb in na:
        shorter, longer = sorted((len(na), len(nb)))
        return max(0.8, shorter / longer)
    return SequenceMatcher(None, na, nb).ratio()


@dataclass(frozen=True)
class Merchant:
    id: str
    canonical: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


class MerchantIndex:
    """別名から店を引く辞書。"""

    def __init__(self, merchants: list[Merchant]) -> None:
        self.merchants = merchants
        self._by_alias: dict[str, str] = {}
        for m in merchants:
            for alias in (m.canonical, *m.aliases):
                key = normalize(alias)
                if key:
                    self._by_alias.setdefault(key, m.id)

    def __len__(self) -> int:
        return len(self.merchants)

    def resolve(self, name: str | None) -> str | None:
        """店名から merchant_id を引く。分からなければ None。"""
        if not name:
            return None
        return self._by_alias.get(normalize(name))

    def canonical_name(self, merchant_id: str) -> str | None:
        return next((m.canonical for m in self.merchants if m.id == merchant_id), None)

    def match_score(self, left: str | None, right: str | None) -> float:
        """2つの店名がどれだけ一致するか。

        辞書で同じ店に解決できたら 1.0。
        できなければ文字列の類似度に落とす。
        """
        if not left or not right:
            return 0.0
        a, b = self.resolve(left), self.resolve(right)
        if a is not None and b is not None:
            return 1.0 if a == b else 0.0
        return similarity(left, right)


def load_merchants(path: Path) -> MerchantIndex:
    if not path.is_file():
        return MerchantIndex([])
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return MerchantIndex(
        [
            Merchant(
                id=m["id"],
                canonical=m["canonical"],
                aliases=tuple(m.get("aliases", []) or ()),
            )
            for m in data.get("merchants", []) or []
        ]
    )
