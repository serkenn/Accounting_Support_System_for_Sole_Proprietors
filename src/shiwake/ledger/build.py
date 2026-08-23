"""documents + links → Beancount（第1部 §6）。

★二重計上を構造的に防ぐのがここ。

同じ支出が「領収書」と「カード明細行」の両方に現れる。
リンクされていれば**1件の仕訳**を作る。2件作ったら破綻する。

仕訳生成の優先順位（第1部 §6）:

  リンク済み          金額はカード明細行、内訳は領収書、貸方はカード
  カード明細行のみ    金額も分類も明細行、貸方はカード
  領収書のみ・現金    領収書、貸方は現金
  領収書のみ・カード  領収書、貸方はカード + pending メタ

★Business と Personal をまたぐときは、資本の科目と持分の科目を
  対で立てる（Q2 の Model A）。混在カードで事業の買い物をすると必ずこれになる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .categorize import Categorizer
from .reconcile import CardLine, Links, Receipt

#: またぎの対向に使う持分の科目（rules/scopes.yaml と揃える）
BRIDGE_ASSET = "Assets:Personal:BusinessInterest"
EQUITY_CONTRIBUTIONS = "Equity:Owner:Contributions"
EQUITY_DRAWINGS = "Equity:Owner:Drawings"

#: Beancount のタグは ASCII のみ。日本語を入れるとパースが落ちる
TAG_PENDING = "pending"

BUSINESS_PREFIXES = (
    "Assets:Business:",
    "Liabilities:Business:",
    "Income:Business:",
    "Expenses:Business:",
)


def _is_business(account: str) -> bool:
    return account.startswith(BUSINESS_PREFIXES)


def _is_personal(account: str) -> bool:
    return ":Personal:" in account


@dataclass
class Posting:
    account: str
    amount: int | None = None

    def render(self) -> str:
        if self.amount is None:
            return f"  {self.account}"
        return f"  {self.account:<48} {self.amount:>12,} JPY"


@dataclass
class Transaction:
    date: date
    payee: str
    narration: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    postings: list[Posting] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def render(self) -> str:
        tags = "".join(f" #{t}" for t in self.tags)
        # ★Beancount は文字列1つだと narration として読む。
        #   payee にするには必ず2つ書く。1つだと取引先が空になる。
        head = f'{self.date.isoformat()} * "{self.payee}" "{self.narration}"'
        lines = [head + tags]
        lines += [f'  {k}: "{v}"' for k, v in sorted(self.meta.items())]
        lines += [p.render() for p in self.postings]
        return "\n".join(lines)

    def balance(self) -> int:
        return sum(p.amount for p in self.postings if p.amount is not None)


@dataclass
class BuildIssue:
    severity: str
    doc_id: str
    message: str

    def format(self) -> str:
        mark = "ERROR  " if self.severity == "error" else "WARNING"
        return f"{mark}  [build] {self.doc_id}: {self.message}"


@dataclass
class BuildResult:
    transactions: list[Transaction] = field(default_factory=list)
    issues: list[BuildIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[BuildIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def render(self, header: str = "") -> str:
        body = "\n\n".join(
            t.render() for t in sorted(self.transactions, key=lambda t: (t.date, t.payee))
        )
        return (header + "\n\n" + body + "\n") if header else body + "\n"


def _bridge(expense_account: str, credit_account: str, amount: int) -> list[Posting]:
    """名前空間をまたぐときの対向を作る（Q2 の Model A）。

    事業の費用を私用の口座で払った場合:

      Expenses:Business:X          +amount   事業の費用
      Equity:Owner:Contributions   -amount   事業主借（事業側で完結）
      Assets:Personal:BusinessInterest +amount 家計側の対向
      Liabilities:Personal:Card    -amount   実際の支払い
    """
    if _is_business(expense_account) and _is_personal(credit_account):
        return [
            Posting(EQUITY_CONTRIBUTIONS, -amount),
            Posting(BRIDGE_ASSET, amount),
        ]
    if not _is_business(expense_account) and credit_account.startswith("Assets:Business:"):
        # 事業の口座で私用の買い物をした → 事業主貸
        return [
            Posting(EQUITY_DRAWINGS, amount),
            Posting(BRIDGE_ASSET, -amount),
        ]
    return []


def _expense_transaction(
    when: date,
    payee: str,
    amount: int,
    expense_account: str,
    credit_account: str,
    meta: dict[str, str],
    narration: str = "",
    tags: list[str] | None = None,
) -> Transaction:
    postings = [Posting(expense_account, amount)]
    bridge = _bridge(expense_account, credit_account, amount)
    if bridge:
        postings.extend(bridge)
        postings.append(Posting(credit_account, -amount))
    else:
        # またがないときは貸方の額を Beancount に推論させる
        postings.append(Posting(credit_account))
    return Transaction(
        date=when, payee=payee, narration=narration, meta=meta, postings=postings, tags=tags or []
    )


def build_month(
    receipts: list[Receipt],
    card_lines: list[CardLine],
    links: Links,
    categorizer: Categorizer,
    receipt_accounts: dict[str, str] | None = None,
    cash_account: str = "Assets:Personal:Cash",
    receipt_payees: dict[str, str] | None = None,
    settlement_accounts: dict[str, str] | None = None,
) -> BuildResult:
    """1か月分の仕訳を組み立てる。

    receipt_accounts: doc_id → 費用の勘定科目（領収書の内訳から決めたもの）
    settlement_accounts: 即時払いの貸方。`"debit_card:0000"` / `"qr_code"` /
        `"ic_card"` のような鍵から勘定科目を引く。
    """
    result = BuildResult()
    receipt_accounts = receipt_accounts or {}
    settlement_accounts = settlement_accounts or {}
    receipt_payees = receipt_payees or {}
    by_doc = {r.doc_id: r for r in receipts}
    by_key = {line.key: line for line in card_lines}

    consumed_lines: set[str] = set()

    # ── 1. リンク済み（領収書 ↔ カード明細行）───────────
    for doc_id, key in sorted(links.links.items()):
        receipt = by_doc.get(doc_id)
        line = by_key.get(key)
        if receipt is None or line is None:
            continue
        consumed_lines.add(key)

        account = receipt_accounts.get(doc_id) or categorizer.categorize(receipt.issuer).account
        if account is None:
            result.issues.append(
                BuildIssue(
                    "error",
                    doc_id,
                    f"勘定科目が決まりません（{receipt.issuer}）。"
                    "rules/categories.yaml に追加してください",
                )
            )
            continue
        if line.amount != receipt.total:
            result.issues.append(
                BuildIssue(
                    "error",
                    doc_id,
                    f"リンク先の明細行 {line.amount:,} と領収書 {receipt.total:,} の額が違います",
                )
            )
            continue

        result.transactions.append(
            _expense_transaction(
                when=line.date,  # ★金額と日付の正はカード明細行
                payee=receipt.issuer,
                amount=line.amount,
                expense_account=account,
                credit_account=line.account,
                meta={"doc_id": doc_id, "card_line": key},
            )
        )

    # ── 2. カード明細行のみ ────────────────────────────
    for line in sorted(card_lines, key=lambda x: (x.date, x.line_id)):
        if line.key in consumed_lines:
            continue
        cat = categorizer.categorize(line.description)
        if cat.account is None:
            result.issues.append(
                BuildIssue(
                    "error",
                    line.key,
                    f"勘定科目が決まりません（{line.description}）。"
                    "rules/categories.yaml に追加してください",
                )
            )
            continue
        result.transactions.append(
            _expense_transaction(
                when=line.date,
                payee=line.description,
                amount=line.amount,
                expense_account=cat.account,
                credit_account=line.account,
                meta={"card_line": line.key},
            )
        )

    # ── 3. 領収書のみ ──────────────────────────────────
    linked_docs = set(links.links)
    for receipt in sorted(receipts, key=lambda r: (r.date, r.doc_id)):
        if receipt.doc_id in linked_docs:
            continue
        account = (
            receipt_accounts.get(receipt.doc_id) or categorizer.categorize(receipt.issuer).account
        )
        if account is None:
            result.issues.append(
                BuildIssue("error", receipt.doc_id, f"勘定科目が決まりません（{receipt.issuer}）")
            )
            continue

        if receipt.payment_method == "cash":
            credit, meta, tags = cash_account, {"doc_id": receipt.doc_id}, []
        elif receipt.payment_method in _IMMEDIATE_METHODS:
            # ★即時払い。あとから請求は来ないので負債を立てない。
            #   引落元が分からないまま適当な口座に落とすと、
            #   その口座の残高が黙って狂う。分からなければ止める。
            credit = _settlement_account(receipt, settlement_accounts)
            if credit is None:
                result.issues.append(
                    BuildIssue(
                        "error",
                        receipt.doc_id,
                        f"{receipt.payment_method} の引落元が決まりません"
                        f"（下4桁 {receipt.card_last4 or 'なし'}）。"
                        "rules/accounts.yaml に登録してください",
                    )
                )
                continue
            meta, tags = {"doc_id": receipt.doc_id}, []
        elif receipt.payment_method is None:
            # ★読めなかった支払手段を、カード払いと決めつけない。
            #   現金だったなら現金が減っているはずで、負債は立たない。
            #   決めつけると現金残高もカード負債も両方まちがう。
            #   仮勘定に置いて、あとで戻ってこられるようにする。
            result.issues.append(
                BuildIssue(
                    "warning",
                    receipt.doc_id,
                    "支払手段が読み取れていません。"
                    f"{UNSETTLED_ACCOUNT} に仮置きしました。"
                    "原本を見て現金かカードかを入れてください",
                )
            )
            credit = UNSETTLED_ACCOUNT
            meta = {"doc_id": receipt.doc_id, "pending": "TRUE"}
            tags = [TAG_PENDING]
        else:
            # ★カード払いだが明細が未取込。届いたらリンクされ pending が外れる
            credit = (
                receipt_accounts.get(f"{receipt.doc_id}:credit")
                or "Liabilities:Personal:CreditCard:Unknown"
            )
            meta = {"doc_id": receipt.doc_id, "pending": "TRUE"}
            tags = [TAG_PENDING]

        result.transactions.append(
            _expense_transaction(
                when=receipt.date,
                payee=receipt.issuer,
                amount=receipt.total,
                expense_account=account,
                credit_account=credit,
                meta=meta,
                tags=tags,
            )
        )

    return result


#: 支払手段が読み取れなかったものの仮置き先。
#:
#: ★カードの負債と混ぜない。混ぜると、実は現金だったものが
#:   カード負債として残り、貸借対照表が静かに狂う。
UNSETTLED_ACCOUNT = "Liabilities:Personal:Unsettled"

#: 即時に決済され、負債を残さない支払手段。
_IMMEDIATE_METHODS = frozenset({"debit_card", "qr_code", "ic_card"})


def _settlement_account(receipt: Receipt, settlement_accounts: dict[str, str]) -> str | None:
    """即時払いの貸方を引く。分からなければ None（推測しない）。"""
    method = str(receipt.payment_method)
    for key in (receipt.card_last4, receipt.account_hint):
        if key:
            found = settlement_accounts.get(f"{method}:{key}")
            if found:
                return found
    return settlement_accounts.get(method)


def card_debit_transaction(
    debit_date: date,
    payee: str,
    liability_account: str,
    bank_account: str,
    amount: int,
    meta: dict[str, str] | None = None,
) -> Transaction:
    """カードの引落（第1部 §6）。締め日で計上した負債を銀行から消し込む。"""
    return Transaction(
        date=debit_date,
        payee=payee,
        meta=meta or {},
        postings=[Posting(liability_account, amount), Posting(bank_account, -amount)],
    )
