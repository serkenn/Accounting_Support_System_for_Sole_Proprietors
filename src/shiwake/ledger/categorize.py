"""勘定科目の自動分類（第1部 §6 / §9.2）。

★分類は**候補**であって確定ではない。
  当てはまるルールが無いものを勝手にどこかへ落とさない。
  未分類は未分類として残し、人が見て `rules/categories.yaml` に足す。
  そうすると次回から決定的に同じ分類になる。

「その他」に落とす既定値をあえて持たない。持つと、
分類できていないことに誰も気づかなくなる。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .merchants import MerchantIndex, normalize


@dataclass(frozen=True)
class CategoryRule:
    id: str
    account: str
    merchant_id: str | None = None
    pattern: str | None = None
    business: bool = False

    def matches(self, merchant_id: str | None, description: str | None) -> bool:
        if self.merchant_id is not None:
            return merchant_id == self.merchant_id
        if self.pattern is not None and description:
            return re.search(self.pattern, normalize(description)) is not None
        return False


@dataclass(frozen=True)
class Categorization:
    account: str | None
    rule_id: str | None
    business: bool = False

    @property
    def resolved(self) -> bool:
        return self.account is not None


class Categorizer:
    def __init__(self, rules: list[CategoryRule], merchants: MerchantIndex) -> None:
        self.rules = rules
        self.merchants = merchants

    def categorize(self, description: str | None) -> Categorization:
        merchant_id = self.merchants.resolve(description)
        for rule in self.rules:
            if rule.matches(merchant_id, description):
                return Categorization(rule.account, rule.id, rule.business)
        # ★既定値を持たない。分からないことを分からないまま返す
        return Categorization(None, None)


def load_categories(path: Path, merchants: MerchantIndex) -> Categorizer:
    if not path.is_file():
        return Categorizer([], merchants)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = [
        CategoryRule(
            id=r["id"],
            account=r["account"],
            merchant_id=(r.get("match") or {}).get("merchant_id"),
            pattern=(r.get("match") or {}).get("pattern"),
            business=bool(r.get("business", False)),
        )
        for r in data.get("rules", []) or []
    ]
    return Categorizer(rules, merchants)
