"""原本に何が起きたかの追記専用の記録（第11部 §5.2）。

原本は Git の外（`/srv/files`）にあるので、そのままでは
訂正・削除の履歴が残らない。ここが電子帳簿保存法の要件に効く。

★`delete` という操作を用意しない。
  差し替えは `supersede` として記録し、旧ファイルも残す。
  「消せない」ことを、機能として実装しない形で担保する。

★このファイルは Phase 24（スキャナ保存）で必要になるが、
  **後から遡って履歴は作れない**ので最初から記録する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Operation = Literal["add", "supersede"]

MANIFEST_NAME = "originals.manifest.jsonl"


@dataclass(frozen=True)
class ManifestEntry:
    op: Operation
    sha256: str
    at: str
    ext: str | None = None
    size: int | None = None
    media_type: str | None = None
    origin: str | None = None
    source_name: str | None = None
    superseded_by: str | None = None
    reason: str | None = None

    def to_json(self) -> str:
        data = {k: v for k, v in self.__dict__.items() if v is not None}
        return json.dumps(data, ensure_ascii=False, sort_keys=True)


class Manifest:
    """追記のみ。既存の行を書き換える手段を提供しない。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, entry: ManifestEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(entry.to_json() + "\n")

    def entries(self) -> list[ManifestEntry]:
        if not self.path.is_file():
            return []
        out: list[ManifestEntry] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            out.append(ManifestEntry(**json.loads(line)))
        return out

    def known_hashes(self) -> set[str]:
        return {e.sha256 for e in self.entries() if e.op == "add"}

    def superseded(self) -> set[str]:
        return {e.sha256 for e in self.entries() if e.op == "supersede"}
