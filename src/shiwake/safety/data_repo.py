"""データリポジトリにアプリのコードが混ざっていないかの検査（第13部 §0）。

分離の前提は「非公開リポジトリにアプリのコードが1行も無い」こと。
無ければ、誤って公開側へ push する経路が構造的に存在しない。

逆に言えば、**ここにコードが入り込んだ瞬間に前提が崩れる**。
作業ディレクトリを間違えるだけで起きるので、人の注意力では防げない。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

#: データリポジトリに存在してよいディレクトリ以外に現れたら止める拡張子
CODE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java"})

#: パッケージの実体を示すディレクトリ名
PACKAGE_DIRS = frozenset({"src", "web", "skills", "fixtures"})

SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".ruff_cache", ".pytest_cache", "var"}
)


@dataclass(frozen=True)
class CodeInDataRepo:
    path: str
    message: str

    def format(self) -> str:
        return f"ERROR   {self.path}  [code_in_data_repo] {self.message}"


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and not SKIP_DIRS & set(path.relative_to(root).parts):
            yield path


def check_no_app_code(root: Path, allow: Iterable[str] = ()) -> list[CodeInDataRepo]:
    """データリポジトリにアプリのコードが無いことを確かめる。"""
    allowed = tuple(allow)
    problems: list[CodeInDataRepo] = []

    for path in _iter_files(root):
        rel = path.relative_to(root)
        if any(str(rel).startswith(a) for a in allowed):
            continue

        if PACKAGE_DIRS & set(rel.parts):
            problems.append(
                CodeInDataRepo(
                    str(rel),
                    "アプリのコードを置くディレクトリです。"
                    "このリポジトリはデータと設定だけを持ちます（第13部 §0）",
                )
            )
            continue

        if path.suffix.lower() in CODE_SUFFIXES:
            problems.append(
                CodeInDataRepo(
                    str(rel),
                    "アプリのコードはここに置きません。公開側のリポジトリで書いてください",
                )
            )
    return problems
