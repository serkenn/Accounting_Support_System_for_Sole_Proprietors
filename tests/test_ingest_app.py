"""投入 API の HTTP 層（第9部 §4.2）。

★認証を外す経路が無いことを、経路ごとに確かめる。
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from conftest import JPEG  # noqa: E402
from shiwake.ingest.access import ACCESS_HEADER  # noqa: E402
from shiwake.ingest.api import IngestSettings  # noqa: E402
from shiwake.ingest.app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    settings = IngestSettings(
        inbox=inbox,
        max_bytes=1024 * 1024,
        access_team_domain="example.cloudflareaccess.com",
        access_aud="aud-value",
    )
    app = create_app(settings)
    return TestClient(app), inbox


CLAIMS = {"email": "user@example.com"}


def _allow(monkeypatch):
    """Access の検証だけを通した状態にする。"""
    monkeypatch.setattr("shiwake.ingest.app.verify_access_token", lambda *a, **k: CLAIMS)
    monkeypatch.setattr("shiwake.ingest.access.JwksCache.get", lambda self: {})


# ── S13 除外を作らない ──────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/api/inbox"), ("get", "/api/inbox/stats")],
)
def test_every_api_route_requires_access(client, method, path):
    c, _inbox = client
    kwargs = {"files": {"file": ("x", JPEG)}} if method == "post" else {}
    response = getattr(c, method)(path, **kwargs)
    assert response.status_code == 401


def test_health_check_needs_no_auth_and_leaks_nothing(client):
    c, _inbox = client
    response = c.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_openapi_is_not_served(client):
    """内部の形を外に出さない。"""
    c, _inbox = client
    assert c.get("/openapi.json").status_code == 404
    assert c.get("/docs").status_code == 404


# ── 正常系 ──────────────────────────────────────────────


def test_upload_stores_the_file(client, monkeypatch):
    _allow(monkeypatch)
    c, inbox = client
    response = c.post(
        "/api/inbox",
        files={"file": ("whatever.txt", JPEG)},
        headers={ACCESS_HEADER: "token"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["duplicate"] is False
    assert (inbox / body["stored_as"]).is_file()


def test_client_filename_is_ignored(client, monkeypatch):
    """★.txt という名前で送っても、中身が JPEG なら .jpg になる。"""
    _allow(monkeypatch)
    c, _inbox = client
    response = c.post(
        "/api/inbox",
        files={"file": (".." + "/" + ".." + "/evil.txt", JPEG)},
        headers={ACCESS_HEADER: "token"},
    )
    assert response.json()["stored_as"].endswith(".jpg")
    assert "evil" not in response.json()["stored_as"]


def test_duplicate_returns_200_not_201(client, monkeypatch):
    _allow(monkeypatch)
    c, _inbox = client
    c.post("/api/inbox", files={"file": ("a", JPEG)}, headers={ACCESS_HEADER: "t"})
    again = c.post("/api/inbox", files={"file": ("a", JPEG)}, headers={ACCESS_HEADER: "t"})
    assert again.status_code == 200
    assert again.json()["duplicate"] is True


def test_rejected_type_gives_415(client, monkeypatch):
    _allow(monkeypatch)
    c, _inbox = client
    response = c.post(
        "/api/inbox",
        files={"file": ("a.svg", b"<svg><script>x()</script></svg>")},
        headers={ACCESS_HEADER: "t"},
    )
    assert response.status_code == 415


def test_stats_report_the_backlog(client, monkeypatch):
    _allow(monkeypatch)
    c, _inbox = client
    c.post("/api/inbox", files={"file": ("a", JPEG)}, headers={ACCESS_HEADER: "t"})
    body = c.get("/api/inbox/stats", headers={ACCESS_HEADER: "t"}).json()
    assert body["count"] == 1
    assert body["oldest"] is not None
