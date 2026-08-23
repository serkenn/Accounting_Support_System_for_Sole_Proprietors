"""即時払いの貸方を rules/accounts.yaml から引く（第1部 §6）。

★デビット・コード決済・電子マネーは「あとで請求が来る」ものではない。
  負債を立てず、その場で資産（銀行口座・チャージ残高）を減らす。

  引落元を取り違えると、その口座の残高だけが黙って狂う。
  **仕訳の貸借は合ったままなので、検算では気づけない。**
  だから引けなかったときは既定値で埋めず、呼び出し側で止める。
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_settlement_accounts(path: Path) -> dict[str, str]:
    """`"debit_card:1234"` / `"ic_card:<id>"` → 勘定科目。"""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}

    for entry in data.get("debit_cards") or []:
        account = entry.get("account")
        if not account:
            continue
        # ★同じカードが売上票に別の下4桁で出ることがある。
        #   別名も同じ口座に行き着かせないと、その支払いだけ止まる。
        last4s = [entry.get("card_last4")]
        last4s += [a.get("card_last4") for a in entry.get("also_appears_as") or []]
        for last4 in last4s:
            if last4:
                out[f"debit_card:{last4}"] = account

    # ★残高は Suica だけではない。コード決済も同じ形で持つ。
    by_method: dict[str, list[str]] = {}
    for entry in data.get("prepaid") or []:
        account = entry.get("account")
        if not (account and entry.get("id")):
            continue
        method = entry.get("method") or "ic_card"
        out[f"{method}:{entry['id']}"] = account
        by_method.setdefault(method, []).append(account)

    # 領収書に残高の名前が無いことがある。その手段の残高が1つしか
    # なければ曖昧さは無いので、手段名だけでも引けるようにする。
    # 2つ以上あるときは引かない（どちらか分からないまま進めない）。
    for method, accounts in by_method.items():
        if len(accounts) == 1:
            out.setdefault(method, accounts[0])

    return out
