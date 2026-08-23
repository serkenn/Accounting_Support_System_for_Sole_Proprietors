"""画面に出す勘定科目の名前（第3部 §4）。

★勘定科目の英語をそのまま画面に出さない。
  「Supplies」ではなく「消耗品費」と出す。税務調査でこの画面を見せながら
  説明できるかが基準なので、決算書と同じ言葉でなければ意味がない。

既定はここに持つ。**科目の木はこのアプリ自身の規約**なので、
アプリが呼び名を知っていてよい（税率や控除額のように年で変わる値ではない）。
非公開側で `rules/labels.yaml` を置けば上書きできる。
"""

from __future__ import annotations

from pathlib import Path

import yaml

#: 費目の集計は `Expenses:<名前空間>:<ここ>` の粒度で行う。
#:
#: 事業側の名前は青色申告決算書の科目名に合わせてある。
#: rules/aoiro_mapping.yaml と食い違うと、画面と決算書で別の言葉になる。
DEFAULT_LABELS: dict[str, str] = {
    # ── 事業（決算書の科目名）─────────────────────────
    "Expenses:Business:Taxes": "租税公課",
    "Expenses:Business:Shipping": "荷造運賃",
    "Expenses:Business:Utilities": "水道光熱費",
    "Expenses:Business:Travel": "旅費交通費",
    "Expenses:Business:Communication": "通信費",
    "Expenses:Business:Advertising": "広告宣伝費",
    "Expenses:Business:Entertainment": "接待交際費",
    "Expenses:Business:Insurance": "損害保険料",
    "Expenses:Business:Repairs": "修繕費",
    "Expenses:Business:Supplies": "消耗品費",
    "Expenses:Business:Depreciation": "減価償却費",
    "Expenses:Business:Welfare": "福利厚生費",
    "Expenses:Business:Outsourcing": "外注工賃",
    "Expenses:Business:Interest": "利子割引料",
    "Expenses:Business:Rent": "地代家賃",
    "Expenses:Business:BankFee": "振込手数料",
    "Expenses:Business:Misc": "雑費",
    # ── 家計 ──────────────────────────────────────────
    "Expenses:Personal:Food": "食費",
    "Expenses:Personal:Housing": "住居費",
    "Expenses:Personal:Transport": "交通費",
    "Expenses:Personal:Communication": "通信費",
    "Expenses:Personal:Education": "教育費",
    "Expenses:Personal:Medical": "医療費",
    "Expenses:Personal:Hardware": "機材・工具",
    "Expenses:Personal:LifeInsurance": "生命保険料",
    "Expenses:Personal:SocialInsurance": "社会保険料",
    "Expenses:Personal:ResidentTax": "住民税",
    "Expenses:Personal:Misc": "その他",
    # ── 収入 ──────────────────────────────────────────
    "Income:Business": "事業収入",
    "Income:Employment": "給与",
    "Income:Other:Scholarship": "奨学金",
    "Income:Other:Misc": "その他の収入",
    # ── 資産・負債（明細や残高の表で使う）──────────────
    "Assets:Personal:Bank": "預金",
    "Assets:Personal:Cash": "現金",
    "Assets:Personal:Prepaid": "電子マネー",
    "Assets:Personal:BusinessInterest": "事業への持分",
    "Assets:Personal:PrepaidTax": "源泉徴収された税",
    "Assets:Business:Cash": "現金（事業）",
    "Assets:Business:FixedAssets": "固定資産",
    "Assets:Business:PrepaidTax": "源泉徴収された税（事業）",
    "Liabilities:Personal:CreditCard": "クレジットカード",
    "Liabilities:Personal:Unsettled": "支払手段が未確認",
    "Equity:Owner:Contributions": "事業主借",
    "Equity:Owner:Drawings": "事業主貸",
    "Equity:Owner:Capital": "元入金",
    "Equity:Opening": "期首残高",
}


def load_labels(path: Path | None = None) -> dict[str, str]:
    """既定に、非公開側の上書きを重ねる。"""
    labels = dict(DEFAULT_LABELS)
    if path and path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, value in (data.get("labels") or {}).items():
            labels[str(key)] = str(value)
    return labels


def label_for(account: str, labels: dict[str, str] | None = None) -> str | None:
    """科目に対応する表示名。**無ければ None を返す。**

    ★英語のまま画面に出すくらいなら、無いことを知らせる。
      黙って英語が出ると、抜けていることに誰も気づかない。
    """
    table = labels if labels is not None else DEFAULT_LABELS
    parts = account.split(":")
    # 長いほうから順に見る。Expenses:Personal:Food:Groceries なら
    # Expenses:Personal:Food で当てる。
    for end in range(len(parts), 1, -1):
        found = table.get(":".join(parts[:end]))
        if found:
            return found
    return None


def missing_labels(accounts: list[str], labels: dict[str, str] | None = None) -> list[str]:
    """表示名の無い科目。`make check` で気づけるようにする。"""
    return sorted({a for a in accounts if label_for(a, labels) is None})
