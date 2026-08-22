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


def test_allowed_types_match_the_spec():
    """第9部 §4.2 の許可リストと一致すること。"""
    assert (
        frozenset({"image/jpeg", "image/png", "image/heic", "image/webp", "application/pdf"})
        == magic.ALLOWED_MEDIA_TYPES
    )


def test_every_detected_format_is_allowed():
    """判定できる形式が許可リストから外れていないこと。"""
    for data in (JPEG, PNG, WEBP, PDF, HEIC):
        fmt = magic.detect(data)
        assert fmt is not None
        assert fmt.media_type in magic.ALLOWED_MEDIA_TYPES
