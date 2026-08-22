"""配信のセキュリティヘッダ（第8部 §2.3・§6・§7）。

★原本ディレクトリは「外部から入ってきたファイル」の置き場。
  信頼しない前提で扱う。ヘッダが1つ欠けるだけで、
  アップロードされたファイル経由の攻撃面が開く。

設定ファイルの中身を検査する。実際のヘッダは Caddy を起動して確認済み。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = ROOT / "docker" / "Caddyfile"


@pytest.fixture(scope="module")
def config() -> str:
    return CADDYFILE.read_text(encoding="utf-8")


def _block(config: str, marker: str) -> str:
    """指定した handle ブロックの中身を取り出す。"""
    start = config.index(marker)
    depth = 0
    for i in range(start, len(config)):
        if config[i] == "{":
            depth += 1
        elif config[i] == "}":
            depth -= 1
            if depth == 0:
                return config[start : i + 1]
    raise AssertionError(f"{marker} のブロックが閉じていません")


def test_config_file_exists():
    assert CADDYFILE.is_file()


# ── /files/*（原本と派生）───────────────────────────────


def test_files_have_nosniff(config):
    """中身から Content-Type を推測させない。"""
    assert 'X-Content-Type-Options "nosniff"' in _block(config, "handle /files/*")


def test_files_have_a_locked_down_csp(config):
    """★万一スクリプトを含むファイルが混ざっても実行させない。"""
    block = _block(config, "handle /files/*")
    assert "default-src 'none'" in block
    assert "sandbox" in block


def test_originals_are_download_only(config):
    """★原本をインライン表示しない。ブラウザに出すのは派生だけ（第8部 §6）。"""
    block = _block(config, "handle /files/*")
    assert "path /files/originals/*" in block
    assert 'Content-Disposition "attachment"' in block


def test_content_addressed_files_are_cached_immutably(config):
    """内容が変わらない限り URL が変わらないので、長期キャッシュしてよい。"""
    block = _block(config, "handle /files/*")
    assert "immutable" in block
    assert "private" in block


def test_server_header_is_removed(config):
    assert "header -Server" in _block(config, "handle /files/*")


# ── SPA ─────────────────────────────────────────────────


def test_spa_falls_back_to_index(config):
    """静的ビルド + SPA フォールバック（第3部 §13）。"""
    assert "try_files {path} /index.html" in config


def test_spa_has_baseline_headers(config):
    block = config[config.index("handle {") :]
    assert 'X-Content-Type-Options "nosniff"' in block
    assert 'X-Frame-Options "DENY"' in block


# ── 設定に固有の情報を書かない（第13部 §7）──────────────


def test_no_domain_or_internal_address(config):
    """★公開リポジトリにドメイン・内部IP・ホスト名を書かない。"""
    assert not re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", config.replace("127.0.0.1", ""))
    assert not re.search(r"[a-z0-9-]+\.(tech|com|net|jp|co\.jp)\b", config)


def test_automatic_https_is_off(config):
    """TLS はリバースプロキシ側で終端する。ここで証明書を取りに行かせない。"""
    assert "auto_https off" in config


def test_admin_endpoint_is_off(config):
    """管理エンドポイントを開けない。"""
    assert "admin off" in config


# ── Dockerfile ──────────────────────────────────────────


def test_container_runs_as_non_root():
    """第1部 §11 S7。"""
    text = (ROOT / "docker" / "Dockerfile.web").read_text(encoding="utf-8")
    assert re.search(r"^USER\s+(?!root)", text, re.MULTILINE)


def test_data_is_not_baked_into_the_image():
    """★実データをイメージに焼き込まない。実行時にマウントする。"""
    text = (ROOT / "docker" / "Dockerfile.web").read_text(encoding="utf-8")
    assert "rm -rf public/data" in text


# ── compose のテンプレート ──────────────────────────────


def test_compose_template_mounts_files_read_only():
    """★Web から原本に書ける経路を作らない（第9部 §6）。"""
    text = (ROOT / "templates" / "deploy" / "compose.yaml.template").read_text(encoding="utf-8")
    assert "/srv/files:ro" in text
    assert "read_only: true" in text


def test_compose_template_has_no_real_values():
    """雛形に固有の値を書かない（第13部 §7）。"""
    text = (ROOT / "templates" / "deploy" / "compose.yaml.template").read_text(encoding="utf-8")
    assert "SYNTHETIC" in text
    assert not re.search(r"[a-z0-9-]+\.(tech|com|net)\b", text)
