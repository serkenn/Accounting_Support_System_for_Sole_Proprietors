"""所得区分と名前空間の検査（第5部 §11 / 第10部 §8 / 第2部 §7.2）。

所得区分を取り違えると申告が誤る。しかも誤りの向きが揃っていない。

  給与を事業の売上に入れる      → 所得を過大に申告する
  奨学金を合計所得金額に入れる  → 扶養・勤労学生控除の判定まで狂う
  家計の資産を B/S に載せる      → 決算書として使えない

どれも「気をつける」で防げる種類のものではないので、
rules/scopes.yaml に規則として書き、ここで機械的に止める。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Posting:
    """1 posting。bean-query の出力から組み立てる。"""

    txn_id: str
    account: str
    number: int
    filename: str
    lineno: int


@dataclass(frozen=True, order=True)
class ScopeIssue:
    guard: str
    severity: Severity
    account: str
    message: str
    location: str = ""

    def format(self) -> str:
        mark = "ERROR  " if self.severity == "error" else "WARNING"
        where = f" {self.location}" if self.location else ""
        return f"{mark}{where}  [{self.guard}] {self.account}: {self.message}"


def matches(pattern: str, account: str) -> bool:
    """勘定科目のパターン一致。

    `*` は「その配下すべて」。**語の途中では当てない** —
    `Income:Business:*` が `Income:BusinessOther` に当たると、
    誤った科目を正しいものとして通してしまう。
    """
    if pattern == "*":
        return True

    if pattern.startswith("*:") and pattern.endswith(":*"):
        middle = pattern[1:-1]  # ":Personal:"
        return middle in f":{account}:"

    if pattern.endswith(":*"):
        prefix = pattern[:-2]
        return account == prefix or account.startswith(prefix + ":")

    return account == pattern


def namespace_of(account: str, namespaces: Sequence[str]) -> str | None:
    parts = account.split(":")
    for ns in namespaces:
        if ns in parts:
            return ns
    return None


@dataclass(frozen=True)
class Guard:
    id: str
    aggregate: str
    forbid: str
    severity: Severity
    reason: str


class Scopes:
    """rules/scopes.yaml の中身。"""

    def __init__(self, data: dict) -> None:
        self._scopes: dict[str, list[str]] = {
            name: list(spec.get("include", [])) for name, spec in data.get("scopes", {}).items()
        }
        self._labels: dict[str, str] = {
            name: spec.get("label", name) for name, spec in data.get("scopes", {}).items()
        }
        self._guards = [
            Guard(
                id=g["id"],
                aggregate=g["aggregate"],
                forbid=g["forbid"],
                severity=g.get("severity", "error"),
                reason=" ".join(str(g.get("reason", "")).split()),
            )
            for g in data.get("guards", [])
        ]
        self._aggregates: dict[str, dict] = data.get("aggregates", {})
        wallets = data.get("household_wallets", {})
        self._wallet_include: list[str] = list(wallets.get("include", []))
        self._wallet_exclude: list[str] = list(wallets.get("exclude", []))

        crossing = data.get("crossing", {})
        self.namespaces: list[str] = list(crossing.get("namespaces", []))
        self.bridge_equity: str = crossing.get("bridge_equity", "")
        self.bridge_asset: str = crossing.get("bridge_asset", "")

    # ── ビューの範囲 ────────────────────────────────

    def in_scope(self, scope: str, account: str) -> bool:
        return any(matches(p, account) for p in self._scopes.get(scope, []))

    def accounts_in_scope(self, scope: str, accounts: Iterable[str]) -> list[str]:
        return [a for a in accounts if self.in_scope(scope, a)]

    # ── 家計の財布 ──────────────────────────────────

    def is_wallet(self, account: str) -> bool:
        """家計の財布か。

        ★家計の「いくら出たか」を決めるのは、何に使ったか（借方）ではなく
          **どの財布から出たか（貸方）**。借方で数えると、事業用口座を
          分けた瞬間に家計の支出が過大になる。

        持分（BusinessInterest）と前払税金は財布ではない。
        使えるお金ではないので、増減しても家計の出入りにはならない。
        """
        if any(matches(p, account) for p in self._wallet_exclude):
            return False
        return any(matches(p, account) for p in self._wallet_include)

    @property
    def has_wallets(self) -> bool:
        return bool(self._wallet_include)

    # ── 集計への混入 ────────────────────────────────

    def check_aggregate(self, aggregate: str, accounts: Iterable[str]) -> list[ScopeIssue]:
        issues: list[ScopeIssue] = []
        guards = [g for g in self._guards if g.aggregate == aggregate]
        allow = self._aggregates.get(aggregate, {}).get("allow", [])
        label = self._aggregates.get(aggregate, {}).get("label", aggregate)

        for account in accounts:
            hit = next((g for g in guards if matches(g.forbid, account)), None)
            if hit is not None:
                issues.append(
                    ScopeIssue(
                        hit.id, hit.severity, account, f"{label}に含めてはいけません。{hit.reason}"
                    )
                )
                continue
            # forbid だけだと、新しい科目が増えたときに黙って混入する
            if allow and not any(matches(p, account) for p in allow):
                issues.append(
                    ScopeIssue(
                        "not_allowed",
                        "error",
                        account,
                        f"{label}に含めてよい科目として宣言されていません。"
                        "rules/scopes.yaml の allow を見直してください",
                    )
                )
        return sorted(issues)

    # ── 名前空間をまたぐ仕訳 ────────────────────────

    def check_crossings(self, postings: Iterable[Posting]) -> list[ScopeIssue]:
        """またぐなら資本の科目を経由していること（第5部 §11）。"""
        issues: list[ScopeIssue] = []
        by_txn: dict[str, list[Posting]] = {}
        for p in postings:
            by_txn.setdefault(p.txn_id, []).append(p)

        for txn_id, group in by_txn.items():
            seen = {ns for p in group if (ns := namespace_of(p.account, self.namespaces))}
            if len(seen) < 2:
                continue
            has_bridge = any(matches(self.bridge_equity, p.account) for p in group)
            if not has_bridge:
                first = group[0]
                issues.append(
                    ScopeIssue(
                        "crossing_without_bridge",
                        "error",
                        " / ".join(sorted(seen)),
                        "事業と家計をまたぐのに資本の科目を経由していません。"
                        f"{self.bridge_equity} と {self.bridge_asset} を対で立ててください",
                        location=f"{first.filename}:{first.lineno} ({txn_id[:8]})",
                    )
                )
        return sorted(issues)

    def check_invariant(self, postings: Iterable[Posting]) -> list[ScopeIssue]:
        """持分と資本の合計がゼロであること（Q2 で選んだモデル）。

        ここが崩れると、事業側・家計側のどちらかの貸借が閉じない。
        """
        total = 0
        for p in postings:
            if matches(self.bridge_asset, p.account) or matches(self.bridge_equity, p.account):
                total += p.number
        if total == 0:
            return []
        return [
            ScopeIssue(
                "bridge_invariant",
                "error",
                f"{self.bridge_asset} + {self.bridge_equity}",
                f"合計が {total:+,} 円で、0 になりません。"
                "事業と家計をまたぐ仕訳のどれかで、対の片方が欠けています",
            )
        ]

    # ── 元帳の科目そのものの検査 ────────────────────

    def check_classification(self, accounts: Iterable[str]) -> list[ScopeIssue]:
        """元帳に実在する科目が、正しく分類されているかを見る。

        check_aggregate() は「集計しようとしている科目の集合」を受け取るので、
        集計を作る側（決算書の出力など）が使う。こちらは元帳そのものを見る。

        2つのことを検査する。

          1. ある集計の allow と forbid の**両方**に当たる科目が無いか
             → 規則が矛盾しているか、科目名が間違っている
          2. 事業の範囲にある科目が、どの集計にも拾われていないか
             → 決算書から黙って落ちる。一番気づきにくい事故
        """
        issues: list[ScopeIssue] = []
        accounts = sorted(set(accounts))

        for account in accounts:
            for name, spec in self._aggregates.items():
                allow = spec.get("allow", [])
                label = spec.get("label", name)
                if not any(matches(p, account) for p in allow):
                    continue
                hit = next(
                    (g for g in self._guards if g.aggregate == name and matches(g.forbid, account)),
                    None,
                )
                if hit is not None:
                    issues.append(
                        ScopeIssue(
                            hit.id,
                            hit.severity,
                            account,
                            f"{label}に含まれてしまいます。{hit.reason}",
                        )
                    )

        claimed = {
            p
            for name, spec in self._aggregates.items()
            if name.startswith("business_")
            for p in spec.get("allow", [])
        }
        for account in accounts:
            if not self.in_scope("business", account):
                continue
            if not any(matches(p, account) for p in claimed):
                issues.append(
                    ScopeIssue(
                        "unmapped_business_account",
                        "error",
                        account,
                        "事業の範囲にありますが、どの集計にも拾われません。"
                        "決算書から黙って落ちます。rules/scopes.yaml の allow と "
                        "rules/aoiro_mapping.yaml を見直してください",
                    )
                )
        return sorted(issues)

    def label(self, scope: str) -> str:
        return self._labels.get(scope, scope)


def load_scopes(path: Path) -> Scopes:
    return Scopes(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
