"""ファイル形式を中身から判定する（第9部 S12 / 第8部 §6）。

★投入時のファイル名を信用しない。拡張子は判定結果から決める。
  原本ディレクトリは「外部から入ってきたファイル」の置き場なので、
  申告された種別を当てにすると、配信時に化ける経路が残る。

許可リスト方式にする。判定できないものは受け取らない。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: 第9部 §4.2 の許可リスト
ALLOWED_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/heic", "image/webp", "application/pdf"}
)

#: 先頭バイトを読む量。ISO-BMFF の ftyp は先頭 32 バイト以内に収まる。
HEADER_BYTES = 64


@dataclass(frozen=True)
class FileFormat:
    media_type: str
    extension: str


_JPEG = FileFormat("image/jpeg", "jpg")
_PNG = FileFormat("image/png", "png")
_WEBP = FileFormat("image/webp", "webp")
_PDF = FileFormat("application/pdf", "pdf")
_HEIC = FileFormat("image/heic", "heic")

#: ISO-BMFF（HEIF 系）のブランド
_HEIF_BRANDS = (b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1")


def detect(data: bytes) -> FileFormat | None:
    """先頭バイトから形式を判定する。判定できなければ None。"""
    if len(data) < 4:
        return None

    if data[:3] == b"\xff\xd8\xff":
        return _JPEG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return _PNG
    if data[:5] == b"%PDF-":
        return _PDF
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _WEBP
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return _HEIC
    return None


def detect_file(path: Path) -> FileFormat | None:
    with path.open("rb") as fh:
        return detect(fh.read(HEADER_BYTES))
