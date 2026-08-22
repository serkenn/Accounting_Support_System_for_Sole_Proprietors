"""紙か電子かの判定（第9部 §9 / Q5(b) の決定）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import HEIC, JPEG, JPEG_WITH_EXIF, PDF, PNG
from shiwake.ingest import origin as og
from shiwake.ingest.magic import detect


def _fmt(data):
    f = detect(data)
    assert f is not None
    return f


# ── 主経路: 投入先のディレクトリで確定する ──────────────


def test_paper_directory_is_confident():
    d = og.resolve(Path("paper/a.heic"), _fmt(HEIC), HEIC)
    assert d.origin == "paper"
    assert d.confident
    assert not d.needs_review


def test_electronic_directory_is_confident():
    d = og.resolve(Path("electronic/a.pdf"), _fmt(PDF), PDF)
    assert d.origin == "electronic"
    assert d.confident


def test_nested_directory_still_resolves():
    d = og.resolve(Path("paper/2026/08/a.jpg"), _fmt(JPEG), JPEG)
    assert d.origin == "paper" and d.confident


def test_directory_beats_content():
    """★中身が電子っぽくても、投入先が paper なら paper。人の指定が正。"""
    d = og.resolve(Path("paper/scan.pdf"), _fmt(PDF), PDF)
    assert d.origin == "paper" and d.confident


# ── 副経路: 直下は推定するが確定しない ──────────────────


@pytest.mark.parametrize("data", [HEIC, JPEG, PDF, PNG])
def test_root_of_inbox_is_never_confident(data):
    """★推測で確定しない（第1部 §9.1）。"""
    d = og.resolve(Path("a.bin"), _fmt(data), data)
    assert not d.confident
    assert d.needs_review


def test_heic_is_estimated_as_paper():
    assert og.resolve(Path("a.heic"), _fmt(HEIC), HEIC).origin == "paper"


def test_pdf_is_estimated_as_electronic():
    assert og.resolve(Path("a.pdf"), _fmt(PDF), PDF).origin == "electronic"


def test_png_is_estimated_as_electronic():
    assert og.resolve(Path("a.png"), _fmt(PNG), PNG).origin == "electronic"


def test_exif_strengthens_the_paper_reason():
    d = og.resolve(Path("a.jpg"), _fmt(JPEG_WITH_EXIF), JPEG_WITH_EXIF)
    assert d.origin == "paper"
    assert "EXIF" in d.reason


def test_reason_tells_the_user_how_to_make_it_confident():
    d = og.resolve(Path("a.jpg"), _fmt(JPEG), JPEG)
    assert "inbox/paper/" in d.reason and "inbox/electronic/" in d.reason
