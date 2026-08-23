"""投入 API（第9部 §4）。

**外出中に撮って積んでおくだけの保管庫。** 解析も仕訳もここではしない。
役割は「失くさないこと」だけで、帰宅後に `/import` が主経路で拾う。

★ここはインターネットに面する唯一の書き込み口である。
  そのため、置ける場所を構造的に1か所に絞ってある。

    S10  マウントは /srv/inbox のみ。元帳も原本も渡さない
    S11  ファイル名をクライアントから受け取らない。サーバ側で採番する
    S12  種別は magic bytes で判定し、許可リスト外を拒否する
    S13  /api/* に Cloudflare Access。**除外を作らない**
    S16  non-root / read-only rootfs

  S11 が効くので、パストラバーサルの経路そのものが存在しない。
  クライアントの文字列がパスに混ざる箇所が1つも無い。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .magic import detect_bytes

#: Web から受け取る種別（第9部 §4.2）。
#:
#: ★取り込み側（`shiwake import`）より狭い。あちらは銀行の CSV も受けるが、
#:   ここは「撮って積む」ための口であって、任意のテキストを投げ込む口ではない。
#:   広げるときは、それが外から書ける範囲を広げることだと理解した上で。
WEB_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/heic", "image/webp", "application/pdf"}
)

#: /import が置いていく「取り込み済みハッシュ」の索引。
#:
#: ★重複判定に originals を見せない。見せた時点で S10 の境界が崩れる。
#:   ハッシュは内容そのものではないので、これだけを渡す。
KNOWN_HASHES = ".known-sha256"

DEFAULT_MAX_BYTES = 25 * 1024 * 1024


class StoreError(Exception):
    """受け取れなかった。理由はそのままクライアントに返してよい。"""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class IngestSettings:
    inbox: Path
    max_bytes: int
    access_team_domain: str
    access_aud: str

    def __post_init__(self) -> None:
        # ★認証の設定が無いまま起動できないようにする。
        #   「とりあえず動かす」ために外せると、外したまま本番に残る。
        if not self.access_team_domain or not self.access_aud:
            raise ValueError(
                "Cloudflare Access の設定がありません。"
                "SHIWAKE_ACCESS_TEAM_DOMAIN と SHIWAKE_ACCESS_AUD を設定してください。"
                "認証なしでは起動しません"
            )

    @property
    def jwks_url(self) -> str:
        return f"https://{self.access_team_domain}/cdn-cgi/access/certs"

    @classmethod
    def from_env(cls) -> IngestSettings:
        return cls(
            inbox=Path(os.environ.get("SHIWAKE_INBOX", "/srv/inbox")),
            max_bytes=int(os.environ.get("SHIWAKE_MAX_BYTES", DEFAULT_MAX_BYTES)),
            access_team_domain=os.environ.get("SHIWAKE_ACCESS_TEAM_DOMAIN", ""),
            access_aud=os.environ.get("SHIWAKE_ACCESS_AUD", ""),
        )


@dataclass(frozen=True)
class Stored:
    sha256: str
    stored_as: str
    size: int
    duplicate: bool


def _known_hashes(inbox: Path) -> set[str]:
    index = inbox / KNOWN_HASHES
    if not index.is_file():
        return set()
    return {line.strip() for line in index.read_text(encoding="utf-8").splitlines() if line.strip()}


def _hashes_in_inbox(inbox: Path) -> set[str]:
    out = set()
    for path in inbox.iterdir():
        if path.is_file() and not path.name.startswith("."):
            out.add(hashlib.sha256(path.read_bytes()).hexdigest())
    return out


def store_upload(
    data: bytes,
    settings: IngestSettings,
    now: datetime,
    hint: dict | None = None,
) -> Stored:
    """受け取ったバイト列を inbox に置く。

    ★引数にファイル名が無いのは意図的である（S11）。
      クライアントの文字列がパスに混ざる経路を作らない。
    """
    if not data:
        raise StoreError("空のファイルです")
    if len(data) > settings.max_bytes:
        raise StoreError(f"大きすぎます（上限 {settings.max_bytes // 1024 // 1024}MB）", status=413)

    fmt = detect_bytes(data)
    if fmt is None or fmt.media_type not in WEB_MEDIA_TYPES:
        raise StoreError(
            "受け取れない種別です。写真（JPEG / PNG / HEIC / WebP）か PDF を送ってください",
            status=415,
        )

    digest = hashlib.sha256(data).hexdigest()
    if digest in _known_hashes(settings.inbox) or digest in _hashes_in_inbox(settings.inbox):
        # ★同じものを2回置かない。同じレシートを2回撮るのはよくある。
        return Stored(sha256=digest, stored_as="", size=len(data), duplicate=True)

    stamp = now.strftime("%Y-%m-%dT%H%M%S")
    name = f"{stamp}_{digest[:8]}.{fmt.extension}"
    target = settings.inbox / name

    # 先に一時ファイルへ書いてから移す。途中で切れた欠けたファイルを
    # /import に拾わせない。
    tmp = settings.inbox / f".{name}.part"
    tmp.write_bytes(data)
    tmp.replace(target)

    if hint:
        # hint は自由記述。**パスには一切使わない**（S11）。
        (settings.inbox / f"{name}.hint.json").write_text(
            json.dumps(hint, ensure_ascii=False), encoding="utf-8"
        )

    return Stored(sha256=digest, stored_as=name, size=len(data), duplicate=False)


@dataclass(frozen=True)
class InboxStats:
    """積んだまま忘れるのが最大のリスク（第9部 §4.4）。

    中身のプレビューは要らない。件数と最古の日付だけでいい。
    """

    count: int
    oldest: str | None


def inbox_stats(inbox: Path) -> InboxStats:
    if not inbox.is_dir():
        return InboxStats(0, None)
    names = sorted(
        p.name
        for p in inbox.iterdir()
        if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".hint.json")
    )
    if not names:
        return InboxStats(0, None)
    # 名前の先頭が採番した時刻なので、並べれば最古が先頭に来る。
    return InboxStats(len(names), names[0][:10])
