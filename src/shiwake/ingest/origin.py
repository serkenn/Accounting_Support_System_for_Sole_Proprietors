"""紙か電子かの判定（第9部 §9）。

この区分で電子帳簿保存法上の扱いが変わる。

  paper       原本は**紙**。写真は参照の便宜。紙を保管していれば要件を満たす
  electronic  原本は**その電子ファイル**。無加工で保存する義務がある

★ファイルの出所は人間しか知らない。中身から確実には判定できない。
  そこで投入先のディレクトリを主経路にし、直下に置かれたものは
  推定したうえで needs_review を立てる。**推測で確定しない。**
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .magic import FileFormat

Origin = Literal["paper", "electronic"]

PAPER_DIR = "paper"
ELECTRONIC_DIR = "electronic"

#: JPEG に EXIF があることを示すマーカー。撮影された可能性を示す弱い手掛かり
_EXIF_MARKER = b"Exif\x00\x00"
_EXIF_SCAN_BYTES = 65536


@dataclass(frozen=True)
class OriginDecision:
    origin: Origin
    confident: bool
    reason: str

    @property
    def needs_review(self) -> bool:
        return not self.confident


def from_directory(relative: Path) -> OriginDecision | None:
    """投入先のディレクトリから決める（主経路）。"""
    parts = relative.parts
    if PAPER_DIR in parts:
        return OriginDecision("paper", True, f"inbox/{PAPER_DIR}/ に投入されました")
    if ELECTRONIC_DIR in parts:
        return OriginDecision("electronic", True, f"inbox/{ELECTRONIC_DIR}/ に投入されました")
    return None


def estimate(fmt: FileFormat, head: bytes) -> OriginDecision:
    """中身から推定する。**確定はしない。**

    手掛かりの強さには差があるが、いずれも決定打にはならない。
    紙をスキャンした PDF も、電子明細を撮った写真も普通に存在する。
    """
    if fmt.media_type == "image/heic":
        return OriginDecision("paper", False, "HEIC はカメラで撮影された可能性が高い形式です")
    if fmt.media_type == "image/jpeg":
        if _EXIF_MARKER in head[:_EXIF_SCAN_BYTES]:
            return OriginDecision("paper", False, "JPEG に EXIF があり、撮影された可能性があります")
        return OriginDecision("paper", False, "JPEG は撮影された可能性がありますが、根拠は弱いです")
    if fmt.media_type == "application/pdf":
        return OriginDecision(
            "electronic",
            False,
            "PDF は電子で受け取った可能性が高いですが、紙をスキャンしたものかもしれません",
        )
    return OriginDecision(
        "electronic", False, f"{fmt.media_type} は電子で受け取った可能性が高い形式です"
    )


def resolve(relative: Path, fmt: FileFormat, head: bytes) -> OriginDecision:
    """投入先を優先し、無ければ推定する。"""
    decided = from_directory(relative)
    if decided is not None:
        return decided
    guess = estimate(fmt, head)
    return OriginDecision(
        guess.origin,
        False,
        f"{guess.reason}。inbox 直下に置かれたため確定できません。"
        f"inbox/{PAPER_DIR}/ か inbox/{ELECTRONIC_DIR}/ に置くと確定します",
    )
