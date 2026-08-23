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

#: 種別ごとに書いてよいキー。
#: ★見慣れないキーがあったら止める。
#:   タイポで設定が黙って無効になるのを防ぐ。実際に一括置換で
#:   debit_day が別の名前に化け、締め日の設定が効かなくなった。
#:   YAML は知らないキーを黙って受け取るので、ここで見るしかない。
#: accounts.yaml のトップレベルに書いてよい節。
KNOWN_SECTIONS = frozenset({"banks", "cards", "debit_cards", "prepaid", "cash"})

KNOWN_KEYS: dict[str, set[str]] = {
    "banks": {
        "id",
        "name",
        "account_type",
        "namespace",
        "account",
        "account_no_last4",
        "branch_code",
        "is_opening_balance_source",
    },
    "cards": {
        "id",
        "name",
        "issuer",
        "brand",
        "namespace",
        "liability_account",
        "card_last4",
        "debit_account",
        "closing_day",
        "debit_day",
        "debit_month_offset",
        "business_day_rule",
        "verified_on",
        "source_url",
        "source_note",
        "contactless",
        "note",
    },
    "debit_cards": {
        "id",
        "name",
        "brand",
        "namespace",
        "card_last4",
        "account",
        "settlement",
        "verified_on",
        "source_note",
    },
    "prepaid": {
        "id",
        "name",
        "kind",
        "namespace",
        "account",
        "charge_from",
        "receipt_available",
    },
}


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

    # ★節の名前を綴り間違えると、その節がまるごと検査されない。
    #   エラーも警告も出ないまま素通りするので、キーの中身より危ない。
    #   実際 `debit_cards:` を `debit_dards:` と書いていて、
    #   デビットカード4件が一度も検査されていなかった。
    unknown_sections = sorted(set(data) - KNOWN_SECTIONS)
    if unknown_sections:
        issues.append(
            RuleIssue(
                "error",
                str(path.name),
                f"知らない節があります: {', '.join(unknown_sections)}。"
                "綴りを確かめてください。節の名前を間違えると、"
                "その節は検査されないまま黙って無視されます",
            )
        )

    groups = (
        ("banks", data.get("banks")),
        ("cards", data.get("cards")),
        # ★デビットは即時支払なので、締め日も引落日も持たない。
        #   クレジットと同じ検査を掛けると、無いものを要求してしまう。
        ("debit_cards", data.get("debit_cards")),
        ("prepaid", data.get("prepaid")),
    )
    for kind, entries in groups:
        for entry in entries or []:
            target = f"{kind}/{entry.get('id', '?')}"

            unknown = sorted(set(entry) - KNOWN_KEYS.get(kind, set()))
            if unknown:
                issues.append(
                    RuleIssue(
                        "error",
                        target,
                        f"知らないキーがあります: {', '.join(unknown)}。"
                        "綴りを確かめてください。YAML は知らないキーを黙って受け取るので、"
                        "タイポがあると設定が効かないまま気づけません",
                    )
                )

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
                issues.extend(_check_contactless(entry, target))
            elif kind == "debit_cards":
                issues.extend(_check_debit_card(entry, target))

    return issues


def _check_contactless(entry: dict, target: str) -> list[RuleIssue]:
    """非接触決済（iD など）の下4桁は、カード本体と違う。

    ★レシートには非接触側の下4桁が出るのに、請求はカード本体にまとまる。
      別のカードとして登録すると、同じ支払いを2つの口座に振り分けてしまう。
    """
    issues: list[RuleIssue] = []
    for item in entry.get("contactless") or []:
        if not item.get("brand"):
            issues.append(RuleIssue("error", target, "contactless に brand がありません"))
        last4 = item.get("card_last4")
        if last4 is not None and not _last4_ok(last4):
            issues.append(RuleIssue("error", target, "contactless の card_last4 は下4桁のみ"))
    return issues


def _check_debit_card(entry: dict, target: str) -> list[RuleIssue]:
    """デビットは締め日を持たないが、**引落元の口座**が正しいことは要る。

    ★ここが違うと、そのカードの支払いが全部まちがった口座から出る。
      しかも元帳の貸借は合うので、検算では気づけない。
    """
    issues: list[RuleIssue] = []
    if not entry.get("account"):
        issues.append(
            RuleIssue("error", target, "account が未設定です。支払いの貸方が決まりません")
        )
    elif not entry.get("verified_on"):
        issues.append(
            RuleIssue(
                "warning",
                target,
                "引落元の口座を確認していません。"
                "ここが違うと支払いが全部まちがった口座から出ます。"
                "確認したら verified_on に日付を入れてください",
            )
        )
    return issues


def _check_card_schedule(entry: dict, target: str) -> list[RuleIssue]:
    """★締め日・引落日が確かめられているか。

    ここが違うと資金繰りの予定日がまるごとズレる。
    しかも**ズレても元帳の貸借は合う**ので、検算では気づけない。
    """
    issues: list[RuleIssue] = []

    # ★引落口座が決まらないと、引落の仕訳そのものが作れない（第1部 §6）。
    #   締め日だけあっても、どこから落ちるか分からなければ元帳に書けない。
    if not entry.get("debit_account"):
        issues.append(
            RuleIssue(
                "warning",
                target,
                "debit_account が未設定です。引落の仕訳が作れません。"
                "明細か会員サイトで引落口座を確認してください",
            )
        )

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
