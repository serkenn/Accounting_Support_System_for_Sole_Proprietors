"""このリポジトリ自身が公開できる状態かを検査する。

Phase 0.5 の受け入れ条件（第13部 §13）を、テストとして常時走らせる。
「公開側に口座番号らしき文字列を含むファイルを置くとコミットできない」を
機械的に保証するのは pre-commit フックだが、フックは無効化できるので
CI 側にも同じ検査を置く。
"""

from __future__ import annotations

from pathlib import Path

from shiwake.safety import public_safe as ps

ROOT = Path(__file__).resolve().parents[1]


def test_no_forbidden_files_are_present():
    problems = ps.check_forbidden_files(ROOT)
    assert not problems, "\n".join(p.format() for p in problems)


def test_all_fixtures_are_declared_synthetic():
    problems = ps.check_fixtures_are_synthetic(ROOT)
    assert not problems, "\n".join(p.format() for p in problems)


def test_tax_templates_ship_no_values():
    """第13部 §8 — 古い税率を同梱して、それを信じた人が誤申告する事態を作らない。"""
    problems = ps.check_tax_templates_are_null(ROOT)
    assert not problems, "\n".join(p.format() for p in problems)


def test_no_sensitive_patterns_in_the_repository():
    findings = [f for f in ps.check_patterns(ROOT) if f.severity == "error"]
    assert not findings, "\n".join(f.format() for f in findings)


def test_hooks_are_executable():
    """フックが実行可能でないと、静かに素通りする。"""
    hooks = ROOT / ".githooks"
    assert hooks.is_dir()
    for name in ("pre-commit", "commit-msg"):
        hook = hooks / name
        assert hook.is_file(), f"{name} がありません"
        assert hook.stat().st_mode & 0o111, f"{name} に実行権限がありません"
