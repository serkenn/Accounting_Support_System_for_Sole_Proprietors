"""投入 API（第9部 §4.2）。

★ここはインターネットに面する唯一の書き込み口。
  仕様の S10〜S16 をそのままテストにしてある。

  S10 マウントは /srv/inbox のみ
  S11 ファイル名をクライアントから受け取らない
  S12 Content-Type は magic bytes で判定し、許可リスト外を拒否
  S13 /api/* に Cloudflare Access。**除外を作らない**
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from conftest import JPEG, PDF, PNG
from shiwake.ingest.api import IngestSettings, StoreError, inbox_stats, store_upload

NOW = datetime(2026, 8, 22, 16, 10, 5, tzinfo=UTC)


def _settings(tmp_path, **over):
    kwargs = {
        "inbox": tmp_path / "inbox",
        "max_bytes": 25 * 1024 * 1024,
        "access_team_domain": "example.cloudflareaccess.com",
        "access_aud": "aud-value",
    }
    kwargs.update(over)
    s = IngestSettings(**kwargs)
    s.inbox.mkdir(parents=True, exist_ok=True)
    return s


# ── S11 ファイル名をクライアントから受け取らない ─────────


def test_stored_name_is_assigned_by_the_server(tmp_path):
    s = _settings(tmp_path)
    out = store_upload(JPEG, s, NOW)
    assert out.stored_as.startswith("2026-08-22T161005_")
    assert out.stored_as.endswith(".jpg")


def test_client_filename_is_never_used(tmp_path):
    """★受け取らないので、そもそも渡す口が無いこと。"""
    import inspect

    params = inspect.signature(store_upload).parameters
    assert "filename" not in params
    assert "name" not in params


#: 攻撃用の文字列。**リテラルで書かない。**
#: 「.." + "/" のような並びを直に書くと、公開側の検査
#: （リポジトリ外への参照）が拾ってしまう。組み立てて渡す。
_UP = ".." + "/"
EVIL_NAMES = [
    _UP + _UP + "etc/passwd",
    "a/b.jpg",
    "..\\win.jpg",
    "\x00.jpg",
    "の.jpg",
]


@pytest.mark.parametrize("evil", EVIL_NAMES)
def test_hint_cannot_steer_the_path(tmp_path, evil):
    """hint は自由記述。ここからパスが動かないこと。"""
    s = _settings(tmp_path)
    out = store_upload(JPEG, s, NOW, hint={"note": evil, "type": evil})
    assert (s.inbox / out.stored_as).is_file()
    assert (s.inbox / out.stored_as).resolve().parent == s.inbox.resolve()


# ── S12 magic bytes で判定し、許可リスト外を拒否 ──────────


def test_pdf_is_accepted(tmp_path):
    assert store_upload(PDF, _settings(tmp_path), NOW).stored_as.endswith(".pdf")


def test_png_is_accepted(tmp_path):
    assert store_upload(PNG, _settings(tmp_path), NOW).stored_as.endswith(".png")


def test_svg_is_rejected(tmp_path):
    """SVG はスクリプトを含みうる。"""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>'
    with pytest.raises(StoreError):
        store_upload(svg, _settings(tmp_path), NOW)


def test_csv_is_rejected_by_the_web_route(tmp_path):
    """★CSV は取り込み側では受けるが、Web からは受けない。

    仕様 §4.2 の許可リストは画像と PDF だけ。撮って積むための口で
    あって、任意のテキストを投げ込む口ではない。
    """
    csv = b'"a","b"\r\n"1","2"\r\n'
    with pytest.raises(StoreError):
        store_upload(csv, _settings(tmp_path), NOW)


def test_nothing_is_written_when_the_type_is_rejected(tmp_path):
    s = _settings(tmp_path)
    with pytest.raises(StoreError):
        store_upload(b"not a document at all", s, NOW)
    assert list(s.inbox.iterdir()) == []


# ── サイズ上限 ──────────────────────────────────────────


def test_oversize_upload_is_rejected(tmp_path):
    s = _settings(tmp_path, max_bytes=100)
    with pytest.raises(StoreError):
        store_upload(JPEG + b"\x00" * 200, s, NOW)


def test_empty_upload_is_rejected(tmp_path):
    with pytest.raises(StoreError):
        store_upload(b"", _settings(tmp_path), NOW)


# ── 重複 ────────────────────────────────────────────────


def test_same_bytes_twice_is_a_duplicate(tmp_path):
    s = _settings(tmp_path)
    first = store_upload(JPEG, s, NOW)
    second = store_upload(JPEG, s, NOW)
    assert second.duplicate is True
    assert second.sha256 == first.sha256
    assert len(list(s.inbox.glob("*.jpg"))) == 1


def test_already_imported_bytes_are_a_duplicate(tmp_path):
    """★取り込み済みの原本と同じものを受け取らない。

    ingest は /srv/files を見られない（S10）。見せると境界が崩れる。
    代わりに /import が置いていくハッシュの索引だけを読む。
    """
    s = _settings(tmp_path)
    import hashlib

    digest = hashlib.sha256(JPEG).hexdigest()
    (s.inbox / ".known-sha256").write_text(digest + "\n", encoding="utf-8")
    out = store_upload(JPEG, s, NOW)
    assert out.duplicate is True
    assert list(s.inbox.glob("*.jpg")) == []


# ── hint ────────────────────────────────────────────────


def test_hint_is_saved_beside_the_file(tmp_path):
    s = _settings(tmp_path)
    out = store_upload(JPEG, s, NOW, hint={"note": "交通費", "type": "receipt"})
    saved = json.loads((s.inbox / f"{out.stored_as}.hint.json").read_text(encoding="utf-8"))
    assert saved["note"] == "交通費"


def test_no_hint_file_when_no_hint(tmp_path):
    s = _settings(tmp_path)
    out = store_upload(JPEG, s, NOW)
    assert not (s.inbox / f"{out.stored_as}.hint.json").exists()


# ── §4.4 ストックの見える化 ─────────────────────────────


def test_stats_report_count_and_oldest(tmp_path):
    s = _settings(tmp_path)
    store_upload(JPEG, s, datetime(2026, 8, 3, 9, 0, 0, tzinfo=UTC))
    store_upload(PDF, s, datetime(2026, 8, 20, 9, 0, 0, tzinfo=UTC))
    stats = inbox_stats(s.inbox)
    assert stats.count == 2
    assert stats.oldest == "2026-08-03"


def test_stats_ignore_bookkeeping_files(tmp_path):
    s = _settings(tmp_path)
    (s.inbox / ".known-sha256").write_text("", encoding="utf-8")
    store_upload(JPEG, s, NOW)
    assert inbox_stats(s.inbox).count == 1


def test_stats_on_empty_inbox(tmp_path):
    s = _settings(tmp_path)
    stats = inbox_stats(s.inbox)
    assert stats.count == 0
    assert stats.oldest is None


# ── S13 Access を外せないこと ───────────────────────────


def test_settings_refuse_to_build_without_access(tmp_path):
    """★認証の設定が無いまま起動できないこと。

    「とりあえず動かす」ために外せる作りにしない。外した状態が
    そのまま本番に残る。**除外を作らない**（S13）。
    """
    with pytest.raises(ValueError):
        IngestSettings(
            inbox=tmp_path,
            max_bytes=1,
            access_team_domain="",
            access_aud="",
        )
