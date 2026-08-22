"""D57 — Beancount との結合をコードで禁止する。

Beancount と beanquery は GPL-2.0-only。本パッケージは MIT なので、
`import` して結合するとライセンスの整合が取れなくなる。
サブプロセス呼び出しに限定するという判断を、機械的に守らせる。

第13部 §9.2 が「設計を後から変えるのは高くつく」と言っているのは
まさにこの境界のこと。ここが緩んだら気づけるようにしておく。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_IMPORT = re.compile(
    r"^\s*(?:from\s+(beancount|beanquery|beangulp)\b|import\s+(beancount|beanquery|beangulp)\b)",
    re.MULTILINE,
)

IGNORE_MARKER = "license-boundary: ignore"


def _python_sources() -> list[Path]:
    skip = {".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build"}
    return [p for p in sorted(ROOT.rglob("*.py")) if not skip & set(p.relative_to(ROOT).parts)]


def test_no_gpl_package_is_imported():
    offenders = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8")
        for m in FORBIDDEN_IMPORT.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            line = text.splitlines()[line_no - 1]
            if IGNORE_MARKER in line:
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{line_no}")
    assert not offenders, (
        "GPL-2.0-only のパッケージを import しています。"
        "bean-check / bean-query はサブプロセスで呼んでください: " + ", ".join(offenders)
    )


def test_gpl_packages_are_not_declared_as_dependencies():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependency_block = text.split("[project.optional-dependencies]")[0]
    for name in ("beancount", "beanquery", "beangulp"):
        assert f'"{name}' not in dependency_block, (
            f"{name} を依存として宣言しています。実行時に外部コマンドとして呼ぶ方針です"
        )


def test_license_boundary_is_documented():
    """判断の理由が残っていること。後から読む人が経緯を追えるように。"""
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "GPL-2.0-only" in notices
    assert "subprocess" in notices
