"""表示用派生の生成（第8部 §3）。

★原本は加工しない。見やすくするのは派生の仕事（第11部 §3.4）。
★派生は再生成できるので、バックアップ対象にしない。
  「全削除 → 再生成で完全復元」をここで担保する（第8部 §7）。
"""

from __future__ import annotations

import pillow_heif
import pytest
from PIL import Image

from shiwake.ingest import derive

pillow_heif.register_heif_opener()

SHA = "a" * 64


# ── 合成データ（実ファイルを持たない。第13部 §5）──────────


def _image(width: int, height: int, colour: str = "white") -> Image.Image:
    img = Image.new("RGB", (width, height), colour)
    # 単色だと圧縮で潰れて向きの検証ができないので、目印を描く
    for x in range(min(width, 40)):
        for y in range(min(height, 8)):
            img.putpixel((x, y), (255, 0, 0))
    return img


def _write(path, img, fmt: str, **kw):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format=fmt, **kw)
    return path


def _pdf(path, pages: int):
    imgs = [_image(600, 800, c) for c in ("white", "ivory", "azure")[:pages]]
    path.parent.mkdir(parents=True, exist_ok=True)
    imgs[0].save(path, format="PDF", save_all=True, append_images=imgs[1:])
    return path


# ── 画像 ────────────────────────────────────────────────


def test_jpeg_produces_thumb_and_view(tmp_path):
    original = _write(tmp_path / "o.jpg", _image(3000, 4000), "JPEG")
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    assert result.thumb and result.thumb.is_file()
    assert result.view and result.view.is_file()
    assert result.page_count == 1


@pytest.mark.parametrize(("name", "long_edge"), [("thumb", 320), ("view", 1600)])
def test_long_edge_is_capped(tmp_path, name, long_edge):
    original = _write(tmp_path / "o.jpg", _image(3000, 4000), "JPEG")
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    with Image.open(getattr(result, name)) as img:
        assert max(img.size) == long_edge


def test_small_originals_are_not_enlarged(tmp_path):
    """★拡大しない。無い解像度を作っても意味がない（第8部 §3.2）。"""
    original = _write(tmp_path / "o.jpg", _image(200, 150), "JPEG")
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    with Image.open(result.view) as img:
        assert img.size == (200, 150)


def test_png_is_supported(tmp_path):
    original = _write(tmp_path / "o.png", _image(800, 600), "PNG")
    assert derive.build_derivatives(original, SHA, tmp_path / "files").view.is_file()


def test_heic_is_supported(tmp_path):
    """★iPhone の既定形式。ここが読めないと日常の主経路が動かない。"""
    original = _write(tmp_path / "o.heic", _image(1200, 900), "HEIF")
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    assert result.view and result.view.is_file()
    with Image.open(result.view) as img:
        assert img.format == "WEBP"


def test_output_is_webp(tmp_path):
    original = _write(tmp_path / "o.jpg", _image(800, 600), "JPEG")
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    for path in (result.thumb, result.view):
        with Image.open(path) as img:
            assert img.format == "WEBP"


# ── 向きと EXIF ─────────────────────────────────────────


def _jpeg_with_orientation(path, orientation: int):
    img = _image(400, 200)
    exif = Image.Exif()
    exif[0x0112] = orientation  # Orientation
    exif[0x8825] = {1: "N", 2: (35.0, 0.0, 0.0)}  # GPSInfo
    exif[0x010F] = "SampleCam"  # Make
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="JPEG", exif=exif)
    return path


def test_orientation_is_applied(tmp_path):
    """★ブラウザ差を持ち込まない。取り込み時に正立させる（第8部 §3.2）。"""
    original = _jpeg_with_orientation(tmp_path / "o.jpg", 6)  # 90度回転が必要
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    with Image.open(original) as src, Image.open(result.view) as out:
        assert src.size == (400, 200)
        assert out.size == (200, 400)  # 回転が適用されている


def test_upright_image_is_unchanged(tmp_path):
    original = _jpeg_with_orientation(tmp_path / "o.jpg", 1)
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    with Image.open(result.view) as out:
        assert out.size == (400, 200)


def test_exif_is_stripped_from_derivatives(tmp_path):
    """★特に GPS。原本には残るので情報は失われない（第8部 §3.2）。"""
    original = _jpeg_with_orientation(tmp_path / "o.jpg", 1)
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    for path in (result.thumb, result.view):
        with Image.open(path) as img:
            assert not dict(img.getexif())
            assert "exif" not in img.info


def test_original_still_has_its_exif(tmp_path):
    """派生から落としても、原本は加工しない。"""
    original = _jpeg_with_orientation(tmp_path / "o.jpg", 1)
    before = original.read_bytes()
    derive.build_derivatives(original, SHA, tmp_path / "files")
    assert original.read_bytes() == before
    with Image.open(original) as img:
        assert dict(img.getexif())


# ── PDF ─────────────────────────────────────────────────


def test_pdf_pages_become_images(tmp_path):
    """★ブラウザで PDF をレンダリングしない（第8部 §3.3）。"""
    original = _pdf(tmp_path / "o.pdf", 3)
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    assert result.page_count == 3
    assert len(result.pages) == 3
    assert [p.name for p in result.pages] == ["p001.webp", "p002.webp", "p003.webp"]
    for page in result.pages:
        with Image.open(page) as img:
            assert img.format == "WEBP"


def test_pdf_gets_thumb_and_view_from_first_page(tmp_path):
    original = _pdf(tmp_path / "o.pdf", 2)
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    assert result.thumb.is_file() and result.view.is_file()


def test_page_limit_is_respected(tmp_path):
    original = _pdf(tmp_path / "o.pdf", 3)
    result = derive.build_derivatives(original, SHA, tmp_path / "files", max_pages=2)
    assert result.page_count == 3  # 実際のページ数は記録する
    assert len(result.pages) == 2  # 生成したのは2枚


# ── 冪等性と再生成（第8部 §3.4・§7）─────────────────────


def test_second_run_is_skipped(tmp_path):
    original = _write(tmp_path / "o.jpg", _image(800, 600), "JPEG")
    files = tmp_path / "files"
    first = derive.build_derivatives(original, SHA, files)
    mtime = first.view.stat().st_mtime_ns
    second = derive.build_derivatives(original, SHA, files)
    assert second.skipped
    assert second.view.stat().st_mtime_ns == mtime


def test_force_regenerates(tmp_path):
    original = _write(tmp_path / "o.jpg", _image(800, 600), "JPEG")
    files = tmp_path / "files"
    derive.build_derivatives(original, SHA, files)
    again = derive.build_derivatives(original, SHA, files, force=True)
    assert not again.skipped


def test_full_delete_then_rebuild_restores_everything(tmp_path):
    """★派生はバックアップ対象にしない。捨ててよいことをここで担保する。"""
    import shutil

    original = _pdf(tmp_path / "o.pdf", 2)
    files = tmp_path / "files"
    first = derive.build_derivatives(original, SHA, files)
    before = {p.name: p.read_bytes() for p in derive.derived_dir(files, SHA).iterdir()}

    shutil.rmtree(files / "derived")
    assert not (files / "derived").exists()

    again = derive.build_derivatives(original, SHA, files)
    after = {p.name: p.read_bytes() for p in derive.derived_dir(files, SHA).iterdir()}
    assert set(before) == set(after)
    assert before == after  # 決定的に同じバイト列に戻る
    assert again.page_count == first.page_count


# ── 失敗の扱い（第8部 §3.4）─────────────────────────────


def test_corrupt_file_reports_an_error_instead_of_raising(tmp_path):
    """★黙って何も出さない状態を作らない。"""
    original = tmp_path / "o.jpg"
    original.write_bytes(b"\xff\xd8\xff" + b"garbage" * 10)
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    assert result.error is not None
    assert result.view is None


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        derive.build_derivatives(tmp_path / "nope.jpg", SHA, tmp_path / "files")


# ── 配置（第8部 §2.2）───────────────────────────────────


def test_derived_path_is_content_addressed(tmp_path):
    files = tmp_path / "files"
    assert derive.derived_dir(files, SHA) == files / "derived" / SHA[:2] / SHA


def test_heic_orientation_cannot_be_verified_synthetically(tmp_path):
    """pillow-heif は保存時に Orientation を 1 へ正規化する。

    合成した HEIC では向きの検証ができない、という事実を固定しておく。
    この前提が変わったら（ライブラリの更新などで）ここが落ちて気づける。
    実機で撮った写真での確認は別途必要。
    """
    img = _image(400, 200)
    exif = Image.Exif()
    exif[0x0112] = 6
    path = tmp_path / "o.heic"
    img.save(path, format="HEIF", exif=exif)
    with Image.open(path) as reopened:
        assert dict(reopened.getexif()).get(0x0112) == 1
        assert reopened.size == (400, 200)


def test_jpeg_orientation_is_the_one_we_can_verify(tmp_path):
    """JPEG では EXIF がそのまま残るので、正立化を実測できる。"""
    original = _jpeg_with_orientation(tmp_path / "o.jpg", 8)  # 反時計回り90度
    result = derive.build_derivatives(original, SHA, tmp_path / "files")
    with Image.open(result.view) as out:
        assert out.size == (200, 400)


# ── プレビューを持たない形式（CSV）──────────────────────


def test_csv_has_no_preview_but_is_not_an_error(tmp_path):
    """★CSV は画像化できないが、それは「失敗」ではない。

    失敗として返すと、UI に「プレビューを生成できませんでした」と出て、
    壊れた原本と見分けがつかなくなる。区別して返す。
    """
    original = tmp_path / "meisai.csv"
    original.write_text('"a","b"\r\n"1","2"\r\n', encoding="utf-8")
    out = derive.build_derivatives(original, "cd" * 32, tmp_path / "files")
    assert out.error is None
    assert out.no_preview is True
    assert out.thumb is None


def test_broken_image_is_still_an_error(tmp_path):
    """no_preview の追加が、本当の失敗を隠す抜け道にならないこと。"""
    original = tmp_path / "broken.jpg"
    original.write_bytes(b"\xff\xd8\xff" + b"\x00" * 64)
    out = derive.build_derivatives(original, "ef" * 32, tmp_path / "files")
    assert out.error is not None
    assert out.no_preview is False
