"""原本の追記専用マニフェスト（第11部 §5.2）。"""

from __future__ import annotations

import json

from shiwake.ingest.manifest import Manifest, ManifestEntry

AT = "2026-08-22T16:10:00+09:00"


def _entry(sha: str, **over):
    base = {"op": "add", "sha256": sha, "at": AT, "ext": "jpg", "size": 1234}
    base.update(over)
    return ManifestEntry(**base)


def test_entries_are_appended(tmp_path):
    m = Manifest(tmp_path / "m.jsonl")
    m.append(_entry("a" * 64))
    m.append(_entry("b" * 64))
    assert [e.sha256 for e in m.entries()] == ["a" * 64, "b" * 64]


def test_appending_never_rewrites_earlier_lines(tmp_path):
    """★訂正削除の履歴が残ることが要件。過去の行を消す手段を持たない。"""
    p = tmp_path / "m.jsonl"
    m = Manifest(p)
    m.append(_entry("a" * 64))
    first = p.read_text(encoding="utf-8")
    m.append(_entry("b" * 64))
    assert p.read_text(encoding="utf-8").startswith(first)


def test_there_is_no_delete_operation():
    """差し替えは supersede。delete という操作を実装しない。"""
    assert not hasattr(Manifest, "delete")
    assert not hasattr(Manifest, "remove")


def test_supersede_records_the_replacement(tmp_path):
    m = Manifest(tmp_path / "m.jsonl")
    m.append(_entry("a" * 64))
    m.append(
        ManifestEntry(
            op="supersede",
            sha256="a" * 64,
            at=AT,
            superseded_by="b" * 64,
            reason="解像度不足のため撮り直し",
        )
    )
    assert m.superseded() == {"a" * 64}
    assert [e.reason for e in m.entries() if e.op == "supersede"] == ["解像度不足のため撮り直し"]


def test_known_hashes_only_counts_additions(tmp_path):
    m = Manifest(tmp_path / "m.jsonl")
    m.append(_entry("a" * 64))
    m.append(ManifestEntry(op="supersede", sha256="a" * 64, at=AT, superseded_by="b" * 64))
    assert m.known_hashes() == {"a" * 64}


def test_missing_file_reads_as_empty(tmp_path):
    assert Manifest(tmp_path / "absent.jsonl").entries() == []


def test_lines_are_valid_json(tmp_path):
    p = tmp_path / "m.jsonl"
    Manifest(p).append(_entry("a" * 64, origin="paper", source_name="IMG_0001.HEIC"))
    row = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert row["origin"] == "paper"
    assert row["op"] == "add"


def test_none_fields_are_omitted(tmp_path):
    p = tmp_path / "m.jsonl"
    Manifest(p).append(_entry("a" * 64))
    row = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert "superseded_by" not in row
