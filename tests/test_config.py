"""パス設定のテスト（第9部 §3.1 / Q5(a) の決定）。"""

from __future__ import annotations

import pytest

from shiwake import config as cfg


def _write(root, main: str, local: str | None = None) -> None:
    (root / cfg.MAIN_CONFIG).write_text(main, encoding="utf-8")
    if local is not None:
        (root / cfg.LOCAL_CONFIG).write_text(local, encoding="utf-8")


def test_absolute_production_paths_are_used_as_is(tmp_path):
    _write(tmp_path, '[paths]\ninbox = "/srv/inbox"\nfiles = "/srv/files"\n')
    c = cfg.load(tmp_path)
    assert str(c.paths.inbox) == "/srv/inbox"
    assert str(c.paths.files) == "/srv/files"


def test_local_override_wins(tmp_path):
    """開発機（macOS）は /srv を作れないので、ここが効かないと動かない。"""
    _write(
        tmp_path,
        '[paths]\ninbox = "/srv/inbox"\nfiles = "/srv/files"\n',
        '[paths]\ninbox = "var/inbox"\nfiles = "var/files"\n',
    )
    c = cfg.load(tmp_path)
    assert c.paths.inbox == tmp_path / "var" / "inbox"


def test_environment_variable_beats_both(tmp_path, monkeypatch):
    _write(
        tmp_path,
        '[paths]\ninbox = "/srv/inbox"\nfiles = "/srv/files"\n',
        '[paths]\ninbox = "var/inbox"\n',
    )
    monkeypatch.setenv("SHIWAKE_INBOX", "/tmp/ci-inbox")
    assert str(cfg.load(tmp_path).paths.inbox) == "/tmp/ci-inbox"


def test_derived_paths_follow_the_spec_layout(tmp_path):
    """第8部 §2.2 のパスの形。MinIO へ移すときはここを保ったまま差し替える。"""
    _write(tmp_path, '[paths]\ninbox = "var/inbox"\nfiles = "var/files"\n')
    p = cfg.load(tmp_path).paths
    assert p.originals == tmp_path / "var" / "files" / "originals"
    assert p.derived == tmp_path / "var" / "files" / "derived"
    assert p.failed == tmp_path / "var" / "inbox" / "failed"


def test_inbox_is_split_by_origin(tmp_path):
    """Q5(b) の決定 — 投入ディレクトリで origin を分ける。"""
    _write(tmp_path, '[paths]\ninbox = "var/inbox"\nfiles = "var/files"\n')
    p = cfg.load(tmp_path).paths
    assert p.inbox_paper == tmp_path / "var" / "inbox" / "paper"
    assert p.inbox_electronic == tmp_path / "var" / "inbox" / "electronic"


def test_missing_paths_section_is_an_error(tmp_path):
    _write(tmp_path, "[safety]\nstrict = true\n")
    with pytest.raises(cfg.ConfigError, match="inbox"):
        cfg.load(tmp_path)


def test_find_root_walks_upwards(tmp_path):
    _write(tmp_path, '[paths]\ninbox = "var/inbox"\nfiles = "var/files"\n')
    deep = tmp_path / "documents" / "2026" / "08"
    deep.mkdir(parents=True)
    assert cfg.find_root(deep) == tmp_path


def test_find_root_raises_when_absent(tmp_path):
    with pytest.raises(cfg.ConfigError):
        cfg.find_root(tmp_path)


def test_safety_section_is_loaded(tmp_path):
    _write(
        tmp_path,
        '[paths]\ninbox = "var/inbox"\nfiles = "var/files"\n'
        '[safety]\nexclude = ["docs/"]\ndenylist = "config/denylist.txt"\n',
    )
    s = cfg.load(tmp_path).safety
    assert s.exclude == ("docs/",)
    assert s.denylist == tmp_path / "config" / "denylist.txt"
