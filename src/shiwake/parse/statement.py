"""カード明細のテキストから明細行を取り出す。

★取り出したら必ず請求総額と検算する。合わなければ抽出漏れであり、
  そのまま進めると二重計上の防止（第1部 §6）の前提が崩れる。
  **合わないときに行を足したり削ったりして合わせない。**

明細の書式はカード会社ごとに違い、同じ会社でも様式が変わる。
どの形にも当たらなかった行を数えて返し、人が気づけるようにする。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

#: 「26/05/14 店名 …… 7,006 …」1行に収まっている形
_ONE_LINE = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{2})\s+"
    r"(?P<name>.+?)\s+"
    r"(?:ご本人|本人|家族)\s+"
    r"(?P<terms>\S+)\s+"
    r"(?:\d{2}/\d{2}\s+)?"
    r"(?P<amount>-?[\d,]+)(?:\s|$)"
)

#: 「26/05/14 店名 7,006 1 1 7,006」支払区分が数字の形
_LEGACY = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{2})\s+"
    r"(?P<name>.+?)\s+"
    r"(?P<amount>-?[\d,]+)\s+"
    r"[０-９0-9]+\s+[０-９0-9]+\s+-?[\d,]+"
)

#: 日付だけの行（次の行に続く）
_DATE_ONLY = re.compile(r"^(\d{2}/\d{2}/\d{2})$")

#: 折り返しを何行まで辿るか
_MAX_WRAP = 4

#: 折り返しの先にある「金額 回数 回数 支払額」の並び
_WRAPPED_AMOUNT = re.compile(r"(-?[\d,]+)\s+[０-９0-9]+\s+[０-９0-9]+\s+-?[\d,]+")

#: 合計額は負になることがある（返品や特典の値引きが多い月）
_TOTAL = re.compile(r"(?:お支払い合計額|ご利用明細合計|お支払金額総合計)\s*[＞>]?\s*(-?[\d,]+)")

#: 明細行ではないが日付で始まりうる行
_NOT_AN_ITEM = re.compile(r"発行|お支払い日|現在判明分")


#: 決済代行の連絡先番号。明細の店名欄にそのまま入ってくる。
#:
#: ★JSON に電話番号を書かない（第1部 §9.1）。使い道も無い。
#:   PDF の折り返しで途中に空白が入ることがあるので、それも吸収する。
_CONTACT_NUMBER = re.compile(r"[（(]\s*[\d\s]{7,}\s*[）)]")

#: 括弧の外に裸で並ぶ長い数字。上と同じ理由で落とす。
_BARE_LONG_DIGITS = re.compile(r"(?<![\d])[\d]{3}\s?[\d]{4,}(?![\d])")


def scrub_description(text: str) -> str:
    """店名から連絡先番号を落とす。

    ★店名そのものは変えない。原本の PDF にも手を触れない。
      JSON に持ち込むものだけを削る。
    """
    out = _CONTACT_NUMBER.sub("", text)
    out = _BARE_LONG_DIGITS.sub("", out)
    return " ".join(out.split())


def _yen(text: str) -> int:
    return int(text.replace(",", "").replace("−", "-"))


def _as_date(raw: str) -> date:
    y, m, d = (int(x) for x in raw.split("/"))
    return date(2000 + y, m, d)


@dataclass(frozen=True)
class StatementLine:
    date: date
    description: str
    amount: int
    foreign_amount: float | None = None
    foreign_currency: str | None = None
    foreign_rate: float | None = None


@dataclass
class StatementParseResult:
    lines: list[StatementLine] = field(default_factory=list)
    declared_total: int | None = None
    #: どの書式にも当たらなかった行。★黙って捨てない
    unparsed: list[str] = field(default_factory=list)

    @property
    def summed(self) -> int:
        return sum(line.amount for line in self.lines)

    @property
    def balanced(self) -> bool:
        """★請求総額と一致するか。ここが合わなければ抽出漏れ。"""
        return self.declared_total is not None and self.summed == self.declared_total

    @property
    def difference(self) -> int | None:
        if self.declared_total is None:
            return None
        return self.declared_total - self.summed


def _foreign(tail: str) -> tuple[float | None, str | None, float | None]:
    m = re.search(r"([\d,]+\.\d{2})\s+([A-Z]{3})\s+([\d.]+)", tail)
    if not m:
        return None, None, None
    return float(m.group(1).replace(",", "")), m.group(2), float(m.group(3))


def parse_card_statement_text(text: str) -> StatementParseResult:
    """明細のテキストから行を取り出す。**確定はしない。**

    ★店名が複数行に折り返され、金額がさらに次の行に来る形がある。
      PDF のテキスト層は見た目の折り返しをそのまま改行にするので、
      1行に収まっている前提で読むと、その分だけ静かに落ちる。
    """
    result = StatementParseResult()

    total = _TOTAL.search(text)
    if total:
        result.declared_total = _yen(total.group(1))

    raw = [line.rstrip() for line in text.splitlines()]
    index = 0
    while index < len(raw):
        line = raw[index].strip()
        index += 1
        if not line or _NOT_AN_ITEM.search(line):
            continue

        matched = False
        for pattern in (_ONE_LINE, _LEGACY):
            m = pattern.match(line)
            if m:
                fa, fc, fr = _foreign(line[m.end("amount") :])
                result.lines.append(
                    StatementLine(
                        date=_as_date(m.group("date")),
                        description=re.sub(r"\s+", " ", m.group("name")).strip(),
                        amount=_yen(m.group("amount")),
                        foreign_amount=fa,
                        foreign_currency=fc,
                        foreign_rate=fr,
                    )
                )
                matched = True
                break
        if matched:
            continue

        head = re.match(r"^(\d{2}/\d{2}/\d{2})(?:\s+(.*))?$", line)
        if not head:
            continue

        # ★折り返しを辿る。金額の並びが現れるまで、次の行を足していく
        parts = [head.group(2) or ""]
        consumed = 0
        found = None
        for offset in range(0, _MAX_WRAP):
            if index + offset >= len(raw):
                break
            nxt = raw[index + offset].strip()
            if _DATE_ONLY.match(nxt) or re.match(r"^\d{2}/\d{2}/\d{2}\s", nxt):
                break  # 次の明細に入った
            parts.append(nxt)
            consumed = offset + 1
            joined = " ".join(parts)
            found = _WRAPPED_AMOUNT.search(joined)
            if found:
                break

        if not found:
            result.unparsed.append(line[:80])
            continue

        joined = " ".join(parts)
        fa, fc, fr = _foreign(joined[found.end() :])
        result.lines.append(
            StatementLine(
                date=_as_date(head.group(1)),
                description=re.sub(r"\s+", " ", joined[: found.start()]).strip()[:60],
                amount=_yen(found.group(1)),
                foreign_amount=fa,
                foreign_currency=fc,
                foreign_rate=fr,
            )
        )
        index += consumed

    return result
