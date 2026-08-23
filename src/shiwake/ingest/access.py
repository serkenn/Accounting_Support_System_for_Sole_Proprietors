"""Cloudflare Access の JWT を検証する（第9部 S13）。

★「/api/* にも Access を適用。**除外を作らない**」。

  Tunnel の内側にいることは認証ではない。Tunnel は経路を作るだけで、
  誰が来たかは何も言わない。ヘッダに載ってくる JWT を、
  Cloudflare の公開鍵で、aud と iss まで含めて検証する。

  aud を見ないと、同じチームの別アプリ向けのトークンが通る。
"""

from __future__ import annotations

import time
from typing import Any

#: Cloudflare Access が JWT を載せてくるヘッダ。
ACCESS_HEADER = "Cf-Access-Jwt-Assertion"

#: 許可する署名方式。**alg を検証側で固定する。**
#: トークンの alg を信用すると `none` や HMAC すり替えの穴が開く。
ALGORITHMS = ["RS256"]

#: JWKS を取り直す間隔（秒）。Cloudflare は鍵を回す。
JWKS_TTL = 3600


class AccessError(Exception):
    """認証できなかった。**理由をクライアントに詳しく返さない。**"""


def verify_access_token(
    token: str,
    jwks: dict[str, Any],
    *,
    aud: str,
    issuer: str,
) -> dict:
    """トークンを検証して claims を返す。通らなければ AccessError。

    jwks: kid → 公開鍵
    """
    import jwt

    if not token:
        raise AccessError("トークンがありません")

    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except Exception as e:  # noqa: BLE001 - 壊れたトークンは全部同じ扱い
        raise AccessError("トークンを読めません") from e

    key = jwks.get(kid) if kid else None
    if key is None:
        raise AccessError("鍵が見つかりません")

    try:
        return jwt.decode(
            token,
            key=key,
            algorithms=ALGORITHMS,
            audience=aud,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud"]},
        )
    except Exception as e:  # noqa: BLE001
        raise AccessError("トークンが無効です") from e


class JwksCache:
    """Cloudflare の公開鍵を取ってきて、しばらく持っておく。

    ★取得に失敗したら、古い鍵で通し続けない。認証を諦めるほうが安全。
    """

    def __init__(self, url: str, ttl: int = JWKS_TTL) -> None:
        self._url = url
        self._ttl = ttl
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0

    def get(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._keys and now - self._fetched_at < self._ttl:
            return self._keys
        self._keys = self._fetch()
        self._fetched_at = now
        return self._keys

    def _fetch(self) -> dict[str, Any]:
        import json
        import urllib.request

        import jwt

        try:
            with urllib.request.urlopen(self._url, timeout=5) as fh:  # noqa: S310
                document = json.loads(fh.read())
        except Exception as e:  # noqa: BLE001
            raise AccessError("公開鍵を取得できません") from e

        keys = {}
        for entry in document.get("keys", []):
            kid = entry.get("kid")
            if not kid:
                continue
            keys[kid] = jwt.PyJWK(entry).key
        if not keys:
            raise AccessError("公開鍵が空です")
        return keys
