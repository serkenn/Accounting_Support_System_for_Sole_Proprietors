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
#
# text/csv を足してある。銀行とカード会社の明細は CSV で配信され、
# 電子取引データは受領した形式のまま保存する必要があるため。
# PDF に変換してから取り込むと、それはもう原本ではない。
ALLOWED_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/heic", "image/webp", "application/pdf", "text/csv"}
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
_CSV = FileFormat("text/csv", "csv")

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


# ── テキスト形式（magic bytes が無い）─────────────────────
#
# CSV は先頭バイトで見分けられない。構造で判定するしかないので、
# 判定はファイル全体を読む detect_file() 側だけに置く。
# detect() は magic bytes 専用のまま残す。

#: 判定に読む上限。数十万行の明細でも先頭数十 KB で形は分かる。
_TEXT_SNIFF_BYTES = 64 * 1024

#: 日本の銀行が出す CSV は今も CP932 が多い。UTF-8 を先に試す。
_TEXT_ENCODINGS = ("utf-8-sig", "cp932")

#: 制御文字。タブと改行だけ許す。1つでもあればテキストではない。
_CONTROL = frozenset(chr(c) for c in range(32)) - {"\t", "\r", "\n"}

#: マークアップの入口。SVG/HTML を CSV として開かせない。
_MARKUP_PREFIXES = ("<", "\ufeff<")


def _decode(data: bytes) -> str | None:
    for encoding in _TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def detect_text(data: bytes) -> FileFormat | None:
    """テキスト形式かどうかを構造から判定する。

    ★許可リスト方式を緩めないため、条件は厳しくとる。
      「区切りが揃った表」だけを CSV とみなす。散文は通さない。
    """
    text = _decode(data)
    if text is None:
        return None
    if text.lstrip().startswith(_MARKUP_PREFIXES):
        return None
    if any(ch in _CONTROL for ch in text):
        return None

    import csv
    import io
    from collections import Counter

    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return None

    # 空行は数えない。末尾の改行で1行増えるのを避ける。
    widths = [len(r) for r in rows if any(cell.strip() for cell in r)]
    if len(widths) < 2:
        return None

    # 最頻の列数が2以上で、かつ過半数の行がそれに揃っていること。
    common, count = Counter(widths).most_common(1)[0]
    if common < 2 or count * 2 <= len(widths):
        return None
    return _CSV


def detect_bytes(data: bytes) -> FileFormat | None:
    """判定の唯一の入口。magic bytes → テキストの順に見る。

    ★呼ぶ側が detect() を直接使うと、テキスト形式を足したときに
      片方の経路だけ直して通らなくなる。実際に一度そうなった。
    """
    fmt = detect(data)
    if fmt is not None:
        return fmt
    return detect_text(data)


def detect_file(path: Path) -> FileFormat | None:
    """★中身だけで決める。ファイル名の拡張子は見ない。"""
    with path.open("rb") as fh:
        # 読むだけで、原本のバイト列には触らない。
        return detect_bytes(fh.read(_TEXT_SNIFF_BYTES))
