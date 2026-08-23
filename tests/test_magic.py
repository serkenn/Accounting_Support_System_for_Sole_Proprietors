"""ファイル形式の判定（第9部 S12 / 第8部 §6）。

★投入時のファイル名を信用しない。拡張子は判定結果から決める。
  原本ディレクトリは外部から入ってきたファイルの置き場なので、
  申告された種別を当てにすると配信時に化ける経路が残る。
"""

from __future__ import annotations

import pytest

from conftest import HEIC, HEIF_MIF1, JPEG, PDF, PNG, WEBP
from shiwake.ingest import magic


@pytest.mark.parametrize(
    ("data", "media_type", "ext"),
    [
        (JPEG, "image/jpeg", "jpg"),
        (PNG, "image/png", "png"),
        (WEBP, "image/webp", "webp"),
        (PDF, "application/pdf", "pdf"),
        (HEIC, "image/heic", "heic"),
        (HEIF_MIF1, "image/heic", "heic"),
    ],
)
def test_known_formats_are_detected(data, media_type, ext):
    fmt = magic.detect(data)
    assert fmt is not None
    assert fmt.media_type == media_type
    assert fmt.extension == ext


def test_unknown_format_returns_none():
    assert magic.detect(b"just some text, not a document") is None


def test_empty_file_returns_none():
    assert magic.detect(b"") is None


def test_svg_is_not_accepted():
    """SVG はスクリプトを含みうる。原本として受け取らない（第8部 §6）。"""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>'
    assert magic.detect(svg) is None


def test_html_disguised_as_image_is_rejected():
    assert magic.detect(b"<!DOCTYPE html><html><body>x</body></html>") is None


def test_extension_comes_from_content_not_filename(tmp_path):
    """★ここが要件。.png という名前の JPEG は jpg として格納される。"""
    p = tmp_path / "receipt.png"
    p.write_bytes(JPEG)
    fmt = magic.detect_file(p)
    assert fmt is not None
    assert fmt.extension == "jpg"


def test_zip_disguised_as_pdf_is_rejected(tmp_path):
    p = tmp_path / "statement.pdf"
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 32)
    assert magic.detect_file(p) is None


def test_detect_file_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        magic.detect_file(tmp_path / "nope.jpg")


#: 第9部 §4.2 に列挙されている形式。
SPEC_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/heic", "image/webp", "application/pdf"}
)

#: 仕様に無いが足したもの。増やすときは必ず理由をここに書く。
#:
#: text/csv — 銀行とカード会社は明細を CSV で配信する。第9部 §4.2 は
#:   撮影・スキャンした証憑を想定していて、電子取引データの配信形式を
#:   数え漏らしている。CSV を受け取れないと PDF に変換してから
#:   取り込むことになり、それは受領した原本ではなくなる。
ADDED_MEDIA_TYPES = frozenset({"text/csv"})


def test_allowed_types_match_the_spec():
    """第9部 §4.2 の許可リストからの差分が、意図した分だけであること。

    ★許可リストが静かに広がるのを止めるための検査。
      形式を1つ増やすことは、原本ディレクトリに入れるものを
      1つ増やすことなので、差分は必ず明示する。
    """
    assert magic.ALLOWED_MEDIA_TYPES == SPEC_MEDIA_TYPES | ADDED_MEDIA_TYPES
    assert magic.ALLOWED_MEDIA_TYPES - SPEC_MEDIA_TYPES == ADDED_MEDIA_TYPES


def test_every_detected_format_is_allowed():
    """判定できる形式が許可リストから外れていないこと。"""
    for data in (JPEG, PNG, WEBP, PDF, HEIC):
        fmt = magic.detect(data)
        assert fmt is not None
        assert fmt.media_type in magic.ALLOWED_MEDIA_TYPES


# ── CSV（銀行・カードの明細は CSV で届く）───────────────
#
# ★電子取引データは「受領した形式のまま」保存する必要がある。
#   CSV を受け取れないと、明細を PDF に変換してから入れることになり、
#   それは原本ではなくなる。
#
# CSV には magic bytes が無いので、判定は構造で行う。
# detect()（先頭バイトのみ）では判定しない。テキストの判定は
# ファイル全体を見る detect_file() 側に置く。


def _sjis(text: str) -> bytes:
    return text.encode("cp932")


BANK_CSV = '"取引日","取引内容","支払金額"\r\n"2026年08月17日","ﾘｿｸ","3"\r\n'


def test_csv_is_not_detected_from_header_bytes_alone():
    """detect() は magic bytes の判定に限る。テキストはここで拾わない。"""
    assert magic.detect(BANK_CSV.encode("utf-8")) is None


def test_utf8_csv_file_is_detected(tmp_path):
    p = tmp_path / "meisai.csv"
    p.write_text(BANK_CSV, encoding="utf-8")
    fmt = magic.detect_file(p)
    assert fmt is not None
    assert fmt.media_type == "text/csv"
    assert fmt.extension == "csv"


def test_shift_jis_csv_file_is_detected(tmp_path):
    """★日本の銀行が出す CSV は今も CP932 が多い。"""
    p = tmp_path / "meisai.csv"
    p.write_bytes(_sjis(BANK_CSV))
    fmt = magic.detect_file(p)
    assert fmt is not None
    assert fmt.media_type == "text/csv"


def test_csv_bytes_are_not_transcoded(tmp_path):
    """★原本を加工しない。判定はしても中身は触らない。"""
    raw = _sjis(BANK_CSV)
    p = tmp_path / "meisai.csv"
    p.write_bytes(raw)
    magic.detect_file(p)
    assert p.read_bytes() == raw


def test_prose_text_is_not_csv(tmp_path):
    """区切りが揃わないものは CSV にしない（許可リスト方式を緩めない）。"""
    p = tmp_path / "notes.txt"
    p.write_text("これはメモです、たぶん\nもう一行\nさらに、もう、一行\n", encoding="utf-8")
    assert magic.detect_file(p) is None


def test_single_line_is_not_csv(tmp_path):
    p = tmp_path / "one.csv"
    p.write_text('"a","b","c"\n', encoding="utf-8")
    assert magic.detect_file(p) is None


def test_html_with_commas_is_not_csv(tmp_path):
    """★マークアップは受け取らない。SVG/HTML の経路を CSV で開かない。"""
    p = tmp_path / "evil.csv"
    p.write_text("<html>\n<body>a,b</body>\n<p>c,d</p>\n</html>\n", encoding="utf-8")
    assert magic.detect_file(p) is None


def test_binary_with_commas_is_not_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes(b"\x00\x01,\x02\x03\n\x04\x05,\x06\x07\n")
    assert magic.detect_file(p) is None


def test_csv_is_in_the_allowlist():
    assert "text/csv" in magic.ALLOWED_MEDIA_TYPES


def test_detect_bytes_covers_both_magic_and_text():
    """★判定の入口を1つにする。

    pipeline が detect() を直接呼んでいたため、許可リストに
    text/csv を足しても CSV が通らなかった。判定経路が2つあると、
    片方だけ直して気づけない。
    """
    assert magic.detect_bytes(JPEG).media_type == "image/jpeg"
    assert magic.detect_bytes(BANK_CSV.encode("utf-8")).media_type == "text/csv"
    assert magic.detect_bytes(b"<html>\n<p>a,b</p>\n<p>c,d</p>\n") is None
