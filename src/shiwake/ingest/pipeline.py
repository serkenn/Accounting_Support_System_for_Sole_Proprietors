"""取り込みのバッチ処理（第9部 §3.3・§3.4）。

「帰宅後にまとめて数十件を処理する」が既定のワークフロー（第9部 §2）。
都度きれいに入力する前提のシステムは続かないので、
**バッチとして成立すること**を設計の前提に置く。

  1件の失敗で全体を止めない
  失敗は理由付きで残す。黙って消さない
  何が起きたかをサマリで出す

★この工程で原本が確定する。したがって次の2つを必ず守る。
  - inbox から originals へ **移動** する（コピーして残さない）
  - 投入時のハッシュと格納後のハッシュが一致することを確かめる
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .derive import build_derivatives
from .magic import ALLOWED_MEDIA_TYPES, detect
from .manifest import Manifest, ManifestEntry
from .origin import resolve

HINT_SUFFIX = ".hint.json"
FAILED_DIR = "failed"
#: 重複は「失敗」ではないので分ける。黙って消しもしない
DUPLICATE_DIR = "duplicates"
ERROR_SUFFIX = ".error.txt"

#: ハッシュ計算の読み出し単位
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Ingested:
    sha256: str
    stored_path: Path
    media_type: str
    extension: str
    size: int
    origin: str
    origin_reason: str
    needs_review: bool
    source_name: str
    hint: dict | None = None
    page_count: int = 1
    derivative_error: str | None = None


@dataclass(frozen=True)
class Failure:
    source_name: str
    reason: str
    moved_to: Path | None


@dataclass(frozen=True)
class Duplicate:
    sha256: str
    source_name: str


@dataclass
class IngestResult:
    scanned: int = 0
    succeeded: list[Ingested] = field(default_factory=list)
    duplicates: list[Duplicate] = field(default_factory=list)
    failed: list[Failure] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "取り込み完了",
            "",
            f"  成功        {len(self.succeeded)}件",
            f"  重複        {len(self.duplicates)}件（スキップ）",
            f"  要レビュー  {sum(1 for i in self.succeeded if i.needs_review)}件",
            f"  失敗        {len(self.failed)}件",
        ]
        broken = [i for i in self.succeeded if i.derivative_error]
        if broken:
            lines.append(f"  プレビュー生成に失敗 {len(broken)}件（原本は取り込み済み）")
        if self.failed:
            lines.append(f"              → inbox/{FAILED_DIR}/ を確認してください")
        return "\n".join(lines)


class IngestError(Exception):
    """1件の取り込みが失敗した。バッチは止めない。"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _scan(inbox: Path) -> Iterator[Path]:
    """inbox を走査する。failed/ は再走査しない。"""
    for path in sorted(inbox.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(inbox)
        if FAILED_DIR in rel.parts or DUPLICATE_DIR in rel.parts:
            continue
        if path.name.endswith(HINT_SUFFIX):
            continue
        yield path


def _read_hint(path: Path) -> dict | None:
    hint_path = path.with_name(path.name + HINT_SUFFIX)
    if not hint_path.is_file():
        return None
    try:
        data = json.loads(hint_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _store_path(files: Path, sha: str, ext: str) -> Path:
    return files / "originals" / sha[:2] / f"{sha}.{ext}"


def _set_aside(inbox: Path, path: Path, directory: str, reason: str) -> Path:
    """inbox から出すが、消さない（第9部 §7）。"""
    dest = inbox / directory
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / path.name
    counter = 1
    while target.exists():
        target = dest / f"{path.stem}_{counter}{path.suffix}"
        counter += 1
    shutil.move(str(path), str(target))
    target.with_name(target.name + ERROR_SUFFIX).write_text(
        f"{reason}\n\n投入時のファイル名: {path.name}\n", encoding="utf-8"
    )
    return target


def _ingest_one(
    path: Path,
    inbox: Path,
    files: Path,
    manifest: Manifest,
    seen: set[str],
    now: str,
    dry_run: bool,
) -> Ingested | Duplicate:
    head = path.open("rb").read(65536)
    fmt = detect(head)
    if fmt is None:
        raise IngestError(
            "ファイルの種別を判定できません。"
            f"受け取れるのは {', '.join(sorted(ALLOWED_MEDIA_TYPES))} です"
        )
    if fmt.media_type not in ALLOWED_MEDIA_TYPES:
        raise IngestError(f"受け取れない種別です: {fmt.media_type}")

    sha = sha256_of(path)
    rel = path.relative_to(inbox)

    if sha in seen:
        if not dry_run:
            _set_aside(
                inbox,
                path,
                DUPLICATE_DIR,
                "既に取り込み済みの内容です。同じレシートを2回撮った場合はこのまま破棄して"
                "構いませんが、別物のつもりだったなら確認してください",
            )
        return Duplicate(sha256=sha, source_name=str(rel))

    decision = resolve(rel, fmt, head)
    stored = _store_path(files, sha, fmt.extension)
    size = path.stat().st_size
    # ★移動する前に読む。移動後は元のパスに無い
    hint = _read_hint(path)

    if not dry_run:
        stored.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(stored))
        # ★原本が変わっていないことを、格納後に必ず確かめる（第9部 §13）
        if sha256_of(stored) != sha:
            raise IngestError("格納後のハッシュが投入時と一致しません。原本が壊れています")
        manifest.append(
            ManifestEntry(
                op="add",
                sha256=sha,
                at=now,
                ext=fmt.extension,
                size=size,
                media_type=fmt.media_type,
                origin=decision.origin,
                source_name=path.name,
            )
        )

    # 表示用派生（第9部 §3.3 ステップ5）。
    # 失敗しても取り込み自体は成功とする。原本は既に確定しているので、
    # 派生はあとから作り直せる。
    page_count = 1
    derivative_error = None
    if not dry_run:
        derived = build_derivatives(stored, sha, files)
        page_count = derived.page_count
        derivative_error = derived.error

    seen.add(sha)
    return Ingested(
        sha256=sha,
        stored_path=stored,
        media_type=fmt.media_type,
        extension=fmt.extension,
        size=size,
        origin=decision.origin,
        origin_reason=decision.reason,
        needs_review=decision.needs_review,
        source_name=str(rel),
        hint=hint,
        page_count=page_count,
        derivative_error=derivative_error,
    )


def ingest(
    inbox: Path,
    files: Path,
    manifest: Manifest,
    dry_run: bool = False,
    on_progress=None,
) -> IngestResult:
    """inbox の全ファイルを originals へ移す。1件の失敗で止めない。"""
    result = IngestResult()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    seen = manifest.known_hashes()

    targets = list(_scan(inbox))
    result.scanned = len(targets)

    for index, path in enumerate(targets, start=1):
        if on_progress is not None:
            on_progress(index, len(targets), path.name)
        try:
            outcome = _ingest_one(path, inbox, files, manifest, seen, now, dry_run)
        except IngestError as e:
            moved = None if dry_run else _set_aside(inbox, path, FAILED_DIR, str(e))
            result.failed.append(Failure(path.name, str(e), moved))
        except OSError as e:
            moved = (
                None
                if dry_run
                else _set_aside(inbox, path, FAILED_DIR, f"読み書きに失敗しました: {e}")
            )
            result.failed.append(Failure(path.name, str(e), moved))
        else:
            if isinstance(outcome, Duplicate):
                result.duplicates.append(outcome)
            else:
                result.succeeded.append(outcome)

    return result
