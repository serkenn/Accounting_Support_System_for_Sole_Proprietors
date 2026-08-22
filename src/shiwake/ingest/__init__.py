"""取り込み（第1部 §13 Phase 1 / 第9部 §3）。

★ここで原本が確定する。以降どんな処理をしても原本は変わらない。
  したがってこの工程だけは、決定的で、やり直せて、
  何が起きたかが後から追える必要がある。
"""

from . import magic, origin
from .manifest import Manifest, ManifestEntry
from .pipeline import IngestResult, ingest, sha256_of

__all__ = [
    "IngestResult",
    "Manifest",
    "ManifestEntry",
    "ingest",
    "magic",
    "origin",
    "sha256_of",
]
