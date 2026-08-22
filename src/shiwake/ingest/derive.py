"""表示用派生の生成（第8部 §3）。

なぜ必要か。

  HEIC   iPhone の既定形式。Safari 以外のブラウザは表示できない
  サイズ 12MP の写真は数MB。一覧を開くと重い
  PDF    ブラウザで直接レンダリングしない（第8部 §3.3）。ページ画像にする

★原本は加工しない。トリミングも傾き補正も明度調整もしない（第11部 §3.4）。
  見やすくするのは派生の仕事であって、原本に触る理由にはならない。

★派生は再生成できる。だから `.gitignore` に入れ、バックアップ対象にもしない。
  それが成り立つことを「全削除 → 再生成で完全復元」のテストで担保している。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pillow_heif
import pypdfium2
from PIL import Image, ImageOps, UnidentifiedImageError

pillow_heif.register_heif_opener()

THUMB_LONG_EDGE = 320
VIEW_LONG_EDGE = 1600
THUMB_QUALITY = 75
VIEW_QUALITY = 85

#: PDF のページ画像化の解像度（第8部 §3.3）
PDF_DPI = 150

#: これを超えるページ数の PDF は先頭だけ生成する（第8部 §3.3）
DEFAULT_MAX_PAGES = 20

THUMB_NAME = "thumb.webp"
VIEW_NAME = "view.webp"


@dataclass
class Derivatives:
    thumb: Path | None = None
    view: Path | None = None
    pages: list[Path] = field(default_factory=list)
    page_count: int = 0
    skipped: bool = False
    error: str | None = None


def derived_dir(files: Path, sha256: str) -> Path:
    """第8部 §2.2 のパス。MinIO へ移すときもこの形を保つ。"""
    return files / "derived" / sha256[:2] / sha256


def _strip_metadata(img: Image.Image) -> Image.Image:
    """EXIF を全部落とす。特に GPS（第8部 §3.2）。

    原本には残るので情報は失われない。派生は配信されるものなので、
    撮影場所が付いたまま出ていく経路を消す。
    """
    # 画素だけを新しい画像へ移す。info（exif を含む）は引き継がない。
    clean = Image.new(img.mode, img.size)
    clean.paste(img)
    return clean


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGB", "L"):
        return img
    if img.mode in ("RGBA", "LA", "P"):
        return img.convert("RGB")
    return img.convert("RGB")


def _save_resized(img: Image.Image, target: Path, long_edge: int, quality: int) -> Path:
    resized = img.copy()
    # ★原本より大きくしない。無い解像度を作っても意味がない
    if max(resized.size) > long_edge:
        resized.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    target.parent.mkdir(parents=True, exist_ok=True)
    resized.save(target, format="WEBP", quality=quality, method=6)
    return target


def _prepare(img: Image.Image) -> Image.Image:
    """向きを正立させ、メタデータを落とす。

    JPEG は EXIF の Orientation を見て回す必要がある。

    HEIC は事情が違う。libheif が容器の回転指定（irot / imir）を
    デコード時に適用し、pillow-heif は EXIF の Orientation を
    保存時に 1 へ正規化する。つまり読んだ時点で正立している。
    exif_transpose はその場合なにもしないので、掛けて害はない。

    ★この HEIC の挙動は合成データでは検証できない（保存時に
      正規化されてしまうため）。実機で撮った写真で一度確認すること。
    """
    upright = ImageOps.exif_transpose(img) or img
    return _strip_metadata(_to_rgb(upright))


def _render_pdf(
    original: Path, out_dir: Path, max_pages: int
) -> tuple[list[Path], int, Image.Image]:
    pdf = pypdfium2.PdfDocument(original)
    try:
        total = len(pdf)
        scale = PDF_DPI / 72
        pages: list[Path] = []
        first: Image.Image | None = None
        for index in range(min(total, max_pages)):
            page = pdf[index]
            image = page.render(scale=scale).to_pil()
            prepared = _strip_metadata(_to_rgb(image))
            if first is None:
                first = prepared
            target = out_dir / f"p{index + 1:03d}.webp"
            pages.append(_save_resized(prepared, target, VIEW_LONG_EDGE, VIEW_QUALITY))
        if first is None:
            raise ValueError("ページがありません")
        return pages, total, first
    finally:
        pdf.close()


def _is_complete(out_dir: Path) -> bool:
    return (out_dir / THUMB_NAME).is_file() and (out_dir / VIEW_NAME).is_file()


def build_derivatives(
    original: Path,
    sha256: str,
    files: Path,
    force: bool = False,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> Derivatives:
    """原本から表示用の派生を作る。

    生成に失敗しても例外を投げない。`error` に理由を入れて返し、
    UI に「プレビュー生成に失敗」と出せるようにする。
    **黙って何も出さない状態を作らない**（第8部 §3.4）。
    """
    if not original.is_file():
        raise FileNotFoundError(original)

    out_dir = derived_dir(files, sha256)
    if not force and _is_complete(out_dir):
        pages = sorted(out_dir.glob("p[0-9][0-9][0-9].webp"))
        return Derivatives(
            thumb=out_dir / THUMB_NAME,
            view=out_dir / VIEW_NAME,
            pages=pages,
            page_count=len(pages) or 1,
            skipped=True,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        if original.suffix.lower() == ".pdf" or original.read_bytes()[:5] == b"%PDF-":
            pages, total, first = _render_pdf(original, out_dir, max_pages)
        else:
            with Image.open(original) as img:
                first = _prepare(img)
            pages, total = [], 1

        thumb = _save_resized(first, out_dir / THUMB_NAME, THUMB_LONG_EDGE, THUMB_QUALITY)
        view = _save_resized(first, out_dir / VIEW_NAME, VIEW_LONG_EDGE, VIEW_QUALITY)
    except (UnidentifiedImageError, OSError, ValueError, pypdfium2.PdfiumError) as e:
        return Derivatives(error=f"プレビューを生成できませんでした: {type(e).__name__}: {e}")

    return Derivatives(thumb=thumb, view=view, pages=pages, page_count=total)


def rebuild_all(
    files: Path, force: bool = True, max_pages: int = DEFAULT_MAX_PAGES
) -> list[Derivatives]:
    """全原本の派生を作り直す（第8部 §7 の復元テストの実体）。"""
    originals = files / "originals"
    results: list[Derivatives] = []
    if not originals.is_dir():
        return results
    for path in sorted(originals.rglob("*")):
        if path.is_file():
            results.append(
                build_derivatives(path, path.stem, files, force=force, max_pages=max_pages)
            )
    return results
