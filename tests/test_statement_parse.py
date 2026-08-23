"""カード明細のパース（第1部 §6 の検算）。

★取り出したら必ず請求総額と検算する。
  合わないのは抽出漏れであり、そのまま進めると
  二重計上の防止の前提が崩れる。
"""

from __future__ import annotations

import textwrap

from shiwake.parse import parse_card_statement_text

ONE_LINE = textwrap.dedent(
    """
    2026年9月 支払い予定分のご利用明細合計 1,806円
    ご利用日 ご利用店名 カード
    26/08/12 サンプルストア／ＮＦＣ ご本人 1回払い 26/09 550
    26/08/12 サンプルストア／ｉＤ ご本人 1回払い 26/09 330
    26/08/12 架空カフェ ご本人 1回払い 26/09 926
    """
)

LEGACY = textwrap.dedent(
    """
    お支払い合計額 14,666円
    ご利用日 ご利用店名
    26/05/14 サンプルストア北店（食品） 7,006 １ １ 7,006
    26/05/15 架空ホームセンター／ＮＦＣ 4,058 １ １ 4,058
    26/05/15
    CLAUDE SUBSCRIPTION (EXAMPLE.COM
    ) 3,602 １ １ 3,602 22.00 USD 163.734 05 15
    ＜お支払金額総合計＞ 14,666
    """
)

WRAPPED = textwrap.dedent(
    """
    お支払い合計額 942円
    26/07/13 架空サービス ＊ＴＲＩＰ ＨＥＬＰ．Ｕ
    Ｂ
    100 １ １ 100
    26/07/12 ５８２２架空ドラッグえきマチ１丁／ｉ
    Ｄ
    842 １ １ 842
    """
)


# ── 検算（第1部 §6）────────────────────────────────────


def test_one_line_format_balances():
    r = parse_card_statement_text(ONE_LINE)
    assert r.declared_total == 1806
    assert r.summed == 1806
    assert r.balanced


def test_legacy_format_balances():
    r = parse_card_statement_text(LEGACY)
    assert r.balanced, f"差 {r.difference}"
    assert len(r.lines) == 3


def test_wrapped_entries_are_not_silently_dropped():
    """★店名が折り返され、金額がさらに次の行に来る形がある。

    1行に収まっている前提で読むと、その分だけ静かに落ちる。
    落ちても合計が合わないので検算で気づけるが、
    そもそも読めるようにしておく。
    """
    r = parse_card_statement_text(WRAPPED)
    assert r.balanced, f"差 {r.difference} / 読めない {r.unparsed}"
    assert len(r.lines) == 2
    assert r.unparsed == []


def test_mismatch_is_reported_not_hidden():
    """★合わないときに行を足したり削ったりして合わせない。"""
    broken = ONE_LINE.replace("1,806円", "9,999円")
    r = parse_card_statement_text(broken)
    assert not r.balanced
    assert r.difference == 9999 - 1806


def test_unparsed_lines_are_kept():
    """どの書式にも当たらなかった行を黙って捨てない。"""
    odd = "お支払い合計額 100円\n26/08/12 読めない形の行\n"
    r = parse_card_statement_text(odd)
    assert r.unparsed


# ── 中身 ────────────────────────────────────────────────


def test_foreign_currency_is_captured():
    """★外貨は証憑の率ではなくカード会社の率が正（第1部 §6）。"""
    r = parse_card_statement_text(LEGACY)
    fx = [x for x in r.lines if x.foreign_currency]
    assert len(fx) == 1
    assert fx[0].foreign_currency == "USD"
    assert fx[0].foreign_amount == 22.0
    assert fx[0].foreign_rate == 163.734
    assert fx[0].amount == 3602


def test_dates_are_parsed_as_this_century():
    r = parse_card_statement_text(ONE_LINE)
    assert r.lines[0].date.year == 2026


def test_negative_amounts_are_kept():
    """返品や特典の値引きは負の額で出る。落とすと合計が合わなくなる。"""
    text = (
        "ご利用明細合計 -5,000円\n"
        "26/08/01 新規ご入会キャンペーン特典 ご本人 1回払い 26/09 -5,000 返品\n"
    )
    r = parse_card_statement_text(text)
    assert r.lines[0].amount == -5000
    assert r.balanced


def test_header_lines_are_not_mistaken_for_items():
    text = (
        "お支払い合計額 550円\n"
        "2026年8月23日現在判明分\n"
        "26/08/12 サンプルストア ご本人 1回払い 26/09 550\n"
    )
    r = parse_card_statement_text(text)
    assert len(r.lines) == 1


def test_empty_text_is_not_an_error():
    r = parse_card_statement_text("")
    assert r.lines == []
    assert r.declared_total is None
    assert not r.balanced


# ── 店名から連絡先番号を落とす（第1部 §9.1）──────────────


def test_payment_processor_contact_number_is_dropped():
    """★JSON に電話番号を書かない。決済代行の番号が店名欄に入ってくる。

    実際に、これが「文脈のない7桁」として redact-check に止められた。
    止まるのが正しい。値のほうを持ち込まない。

    ★番号はここでも組み立てる。リテラルで書くと、合成値でも
      同じ検査に止められる（止まるのが正しい）。
    """
    from shiwake.parse.statement import scrub_description

    number = "9" * 3 + " " + "9" * 7
    raw = f"PAYPAL *SAMPLESYSTEM SAMPLE({number} )"
    out = scrub_description(raw)
    assert "9" * 7 not in out
    assert "SAMPLE" in out


def test_ordinary_store_name_survives():
    from shiwake.parse.statement import scrub_description

    assert scrub_description("セブン－イレブン／ｉＤ") == "セブン－イレブン／ｉＤ"
    assert scrub_description("５８２２マツモトキヨシえきマチ１丁／ｉＤ").startswith("５８２２")


def test_short_numbers_are_kept():
    """店番号のような短い数字は残す。名前の一部になっている。"""
    from shiwake.parse.statement import scrub_description

    assert scrub_description("ジョイフル 123") == "ジョイフル 123"
