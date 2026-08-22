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


def test_every_source_file_is_tracked_by_git():
    """★ソースが .gitignore に巻き込まれていないこと。

    データ用のディレクトリ名（ledger/ など）をアンカー無しで無視すると、
    同名のソースディレクトリまで巻き込む。手元では動くので気づけない。
    """
    import subprocess

    tracked = set(
        subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "src"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    )
    on_disk = {
        str(p.relative_to(ROOT))
        for p in (ROOT / "src").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    missing = sorted(on_disk - tracked)
    assert not missing, "git が追跡していないソースがあります: " + ", ".join(missing)


def test_tests_do_not_reach_outside_the_repository():
    """★公開側のテストは公開側だけで完結すること（第13部 §5）。

    非公開リポジトリを参照すると、それが無い環境（CI・他人の手元）で落ちる。
    しかも手元では通るので気づけない。
    """
    import re

    offenders = []
    pattern = re.compile(r"parents\[\s*[2-9]\s*\]|\.\./\.\.|ledger-data")
    this_file = Path(__file__).name
    for path in sorted((ROOT / "tests").glob("*.py")):
        if path.name == this_file:
            continue  # この検査自身のパターン文字列に反応させない
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{path.name}:{lineno}")
    assert not offenders, "リポジトリの外を参照しています: " + ", ".join(offenders)


def test_makefile_does_not_require_the_private_repository():
    """make check が非公開リポジトリ前提だと、公開側だけでは通らない。"""
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    for line in text.splitlines():
        if "ledger-data" in line and not line.lstrip().startswith("#"):
            # DENYLIST は「あれば使う」形なので許す
            assert "DENYLIST" in line, f"非公開リポジトリに依存しています: {line.strip()}"
