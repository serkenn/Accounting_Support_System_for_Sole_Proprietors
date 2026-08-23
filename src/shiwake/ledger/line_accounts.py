"""カード明細1行ごとの科目の指定（第1部 §7）。

★店名だけで分類が決まらない店がある。Amazon も百均も、
  事業の部品を買うこともあれば私用のこともある。

  `rules/categories.yaml` に書くと、**都度の判断を機械が勝手に上書きする。**
  領収書があれば `lines[].account` で指定できるが、
  カード明細にしか現れない支払いには領収書が無い。そのための置き場。

★ここに無い行は、既定に落とさずビルドを止める。
  「その他」に落ちた瞬間、分類できていないことに誰も気づかなくなる。
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_line_accounts(path: Path | None) -> dict[str, str]:
    """`"<statement_doc_id>:<line_id>"` → 勘定科目。"""
    if not path or not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in (data.get("lines") or {}).items() if v}


def stub_for(undecided: list[tuple[str, str, int]]) -> str:
    """決まっていない行を、そのまま貼れる YAML にして返す。

    ★人にやってもらう作業は、貼るだけで済む形にする。
      1行ずつ書き写させると、写し間違いが混ざる。
    """
    if not undecided:
        return ""
    out = ["lines:"]
    for key, description, amount in undecided:
        out.append(f"  # {description}  {amount:,}円")
        out.append(f'  "{key}": ')
    return "\n".join(out)
