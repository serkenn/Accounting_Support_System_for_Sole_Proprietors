"""公開リポジトリに入れてはいけないものの検査（第13部 §6.2）。

第1層（名前ベース）はローカルの pre-commit が担う。ここは第2層で、
**パターンと構造**だけで判断する。名前の一覧を公開側に置けないため
（一覧そのものが個人情報になる。第13部 §6.1）。

したがってこの検査は「最後の網」であって、本命ではない。
公開 CI で検出できた時点で、既に push されている。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from .denylist import Denylist
from .findings import Finding
from .scanner import Scanner

#: 公開側に存在してはいけないファイル
FORBIDDEN_GLOBS = (
    ".env",
    ".env.*",
    "*.tsr",
    "secrets*",
    "*secrets.*",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
    "*.pem",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
)

SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
    }
)

SYNTHETIC_MARKER = "SYNTHETIC"

TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".md",
        ".txt",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".css",
        ".html",
        ".beancount",
        ".csv",
        ".cfg",
        ".ini",
    }
)


@dataclass(frozen=True)
class Problem:
    kind: str
    path: str
    message: str

    def format(self) -> str:
        return f"ERROR   {self.path}  [{self.kind}] {self.message}"


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS & set(path.relative_to(root).parts):
            continue
        yield path


def check_forbidden_files(root: Path) -> list[Problem]:
    problems: list[Problem] = []
    for path in _iter_files(root):
        rel = path.relative_to(root)
        for pattern in FORBIDDEN_GLOBS:
            if rel.name == pattern or rel.match(pattern):
                problems.append(
                    Problem(
                        "forbidden_file",
                        str(rel),
                        "公開リポジトリに置いてはいけない種類のファイルです",
                    )
                )
                break
    return problems


def check_fixtures_are_synthetic(root: Path) -> list[Problem]:
    """fixtures/ が合成データであることを機械的に担保する（第13部 §5）。

    テキストはファイル内に SYNTHETIC マーカーを要求する。
    画像などのバイナリは fixtures/MANIFEST.yaml に由来を書かせる。
    """
    fixtures = root / "fixtures"
    if not fixtures.is_dir():
        return []

    manifest_path = fixtures / "MANIFEST.yaml"
    listed: set[str] = set()
    problems: list[Problem] = []

    if manifest_path.is_file():
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        for entry in data.get("files", []) or []:
            if isinstance(entry, dict) and entry.get("path"):
                if not entry.get("synthetic"):
                    problems.append(
                        Problem(
                            "fixture_not_synthetic",
                            f"fixtures/{entry['path']}",
                            "MANIFEST.yaml で synthetic: true が宣言されていません",
                        )
                    )
                if not entry.get("how_made"):
                    problems.append(
                        Problem(
                            "fixture_no_provenance",
                            f"fixtures/{entry['path']}",
                            "MANIFEST.yaml に how_made（作成方法）がありません",
                        )
                    )
                listed.add(str(entry["path"]))

    for path in _iter_files(fixtures):
        rel = path.relative_to(fixtures)
        if rel.name == "MANIFEST.yaml":
            continue
        if str(rel) in listed:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = ""
            if SYNTHETIC_MARKER not in text:
                problems.append(
                    Problem(
                        "fixture_not_synthetic",
                        str(path.relative_to(root)),
                        f"{SYNTHETIC_MARKER} マーカーがありません",
                    )
                )
        else:
            problems.append(
                Problem(
                    "fixture_unlisted",
                    str(path.relative_to(root)),
                    "バイナリのフィクスチャは fixtures/MANIFEST.yaml に由来を記載してください",
                )
            )
    return problems


#: 税務の「値」ではないので、テンプレートでも中身があってよいキー
_METADATA_KEY = re.compile(r"(?:^|_)(?:note|description|source_url|url|checked_on|checked_by)$")


def _all_null(node: object) -> bool:
    if node is None:
        return True
    if isinstance(node, dict):
        return all(_all_null(v) for k, v in node.items() if not _METADATA_KEY.search(str(k)))
    if isinstance(node, list):
        return all(_all_null(v) for v in node)
    if isinstance(node, str):
        return node.strip() == ""
    return False


def check_tax_templates_are_null(root: Path) -> list[Problem]:
    """税率・控除額を同梱しない（第13部 §8）。

    古い値が入ったまま配ると、それを信じた人が誤った申告をする。
    """
    problems: list[Problem] = []
    templates = root / "templates"
    if not templates.is_dir():
        return problems
    for path in sorted(templates.rglob("*.yaml")):
        if "tax" not in path.relative_to(templates).parts and "tax" not in path.stem.lower():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, value in data.items() if isinstance(data, dict) else []:
            if key in {"_meta", "version", "schema_version"}:
                continue
            if not _all_null(value):
                problems.append(
                    Problem(
                        "tax_template_not_null",
                        str(path.relative_to(root)),
                        f"'{key}' に値が入っています。テンプレートの税務値は null にしてください",
                    )
                )
    return problems


def check_patterns(root: Path, denylist: Denylist | None = None) -> list[Finding]:
    """パターンベースの検査を全ファイルに掛ける（strict）。"""
    scanner = Scanner(denylist=denylist, strict=True)
    findings: list[Finding] = []
    for path in _iter_files(root):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        findings.extend(scanner.scan_file(path))
    return findings


def check_commit_messages(root: Path, denylist: Denylist | None, limit: int = 200) -> list[Finding]:
    """コミットメッセージにも固有名詞は漏れる（第13部 §6.3）。"""
    if not denylist:
        return []
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", f"-{limit}", "--format=%H%n%s%n%b%n%x00"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return []
    scanner = Scanner(denylist=denylist)
    findings: list[Finding] = []
    for chunk in out.split("\x00"):
        chunk = chunk.strip()
        if not chunk:
            continue
        sha, _, body = chunk.partition("\n")
        findings.extend(
            Finding(
                path=f"commit {sha[:12]}",
                line=f.line,
                rule=f.rule,
                severity=f.severity,
                message=f.message,
                excerpt=f.excerpt,
            )
            for f in scanner.scan_commit_message(body)
        )
    return findings


def run_gitleaks(root: Path) -> tuple[bool, str]:
    """gitleaks があれば実行する（第1部 §11 S5）。無ければスキップを報告する。"""
    if shutil.which("gitleaks") is None:
        return True, "gitleaks: 未インストールのためスキップしました（CI では必須）"
    proc = subprocess.run(
        ["gitleaks", "detect", "--source", str(root), "--no-banner", "--redact"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return True, "gitleaks: 検出なし"
    return False, "gitleaks: 検出あり（詳細は gitleaks を直接実行して確認してください）"
