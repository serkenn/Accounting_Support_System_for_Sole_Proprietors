"""Cloudflare Access の検証（第9部 S13）。

★「/api/* にも Access を適用。**除外を作らない**」。
  ここが素通りすると、投入 API が誰でも書ける口になる。
"""

from __future__ import annotations

import time

import pytest

from shiwake.ingest.access import AccessError, verify_access_token

pytest.importorskip("jwt")

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

TEAM = "example.cloudflareaccess.com"
AUD = "aud-value"
ISSUER = f"https://{TEAM}"


@pytest.fixture(scope="module")
def keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, {"kid": "k1", "key": key.public_key()}


def _token(keys, **over):
    key, pub = keys
    claims = {
        "aud": [AUD],
        "iss": ISSUER,
        "exp": int(time.time()) + 600,
        "iat": int(time.time()) - 10,
        "email": "user@example.com",
    }
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": pub["kid"]})


def _jwks(keys):
    _key, pub = keys
    return {pub["kid"]: pub["key"]}


def test_valid_token_is_accepted(keys):
    claims = verify_access_token(_token(keys), _jwks(keys), aud=AUD, issuer=ISSUER)
    assert claims["email"] == "user@example.com"


def test_missing_token_is_rejected(keys):
    with pytest.raises(AccessError):
        verify_access_token("", _jwks(keys), aud=AUD, issuer=ISSUER)


def test_expired_token_is_rejected(keys):
    with pytest.raises(AccessError):
        verify_access_token(
            _token(keys, exp=int(time.time()) - 60), _jwks(keys), aud=AUD, issuer=ISSUER
        )


def test_wrong_audience_is_rejected(keys):
    """★別のアプリ向けのトークンを使い回せないこと。"""
    with pytest.raises(AccessError):
        verify_access_token(_token(keys), _jwks(keys), aud="other-aud", issuer=ISSUER)


def test_wrong_issuer_is_rejected(keys):
    with pytest.raises(AccessError):
        verify_access_token(
            _token(keys), _jwks(keys), aud=AUD, issuer="https://evil.cloudflareaccess.com"
        )


def test_unknown_key_id_is_rejected(keys):
    with pytest.raises(AccessError):
        verify_access_token(_token(keys), {}, aud=AUD, issuer=ISSUER)


def test_unsigned_token_is_rejected(keys):
    """★alg: none を通さない。署名検証を飛ばす古典的な穴。"""
    import base64
    import json as _json

    def b64(obj):
        return base64.urlsafe_b64encode(_json.dumps(obj).encode()).rstrip(b"=").decode()

    forged = f"{b64({'alg': 'none', 'kid': 'k1'})}.{b64({'aud': [AUD], 'iss': ISSUER})}."
    with pytest.raises(AccessError):
        verify_access_token(forged, _jwks(keys), aud=AUD, issuer=ISSUER)


def test_token_signed_by_another_key_is_rejected(keys):
    """★kid だけ合わせても、鍵が違えば通らないこと。"""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {"aud": [AUD], "iss": ISSUER, "exp": int(time.time()) + 600},
        other,
        algorithm="RS256",
        headers={"kid": "k1"},
    )
    with pytest.raises(AccessError):
        verify_access_token(forged, _jwks(keys), aud=AUD, issuer=ISSUER)
