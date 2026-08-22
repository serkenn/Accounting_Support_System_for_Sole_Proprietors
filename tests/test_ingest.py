"""取り込み（第1部 Phase 1 / 第9部 §3）。

★ここで原本が確定する。以降どんな処理をしても原本は変わらない。
  したがって、投入時のハッシュと格納後のハッシュが一致することが
  この工程の最低条件（第9部 §13）。
"""

from __future__ import annotations

import hashlib

from conftest import HEIC, JPEG, PDF, PNG
from shiwake.ingest.manifest import Manifest
from shiwake.ingest.pipeline import ingest


def _paths(tmp_path):
    inbox = tmp_path / "inbox"
    files = tmp_path / "files"
    (inbox / "paper").mkdir(parents=True, exist_ok=True)
    (inbox / "electronic").mkdir(parents=True, exist_ok=True)
    return inbox, files


def _put(inbox, relative, data):
    p = inbox / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(tmp_path, **kw):
    inbox, files = _paths(tmp_path)
    return ingest(inbox=inbox, files=files, manifest=Manifest(tmp_path / "m.jsonl"), **kw)


# ── 原本の確定 ──────────────────────────────────────────


def test_file_is_moved_not_copied(tmp_path):
    """★inbox に残さない。残すと二重に取り込む経路ができる（第9部 §13）。"""
    inbox, files = _paths(tmp_path)
    src = _put(inbox, "paper/receipt.jpg", JPEG)
    _run(tmp_path)
    assert not src.exists()


def test_hash_is_unchanged_by_ingestion(tmp_path):
    """★ここが一致しなければ設計が壊れている（第9部 §13）。"""
    inbox, files = _paths(tmp_path)
    _put(inbox, "paper/receipt.jpg", JPEG)
    result = _run(tmp_path)
    stored = files / "originals" / _sha(JPEG)[:2] / f"{_sha(JPEG)}.jpg"
    assert stored.is_file()
    assert _sha(stored.read_bytes()) == _sha(JPEG)
    assert result.succeeded[0].sha256 == _sha(JPEG)


def test_path_is_content_addressed(tmp_path):
    inbox, files = _paths(tmp_path)
    _put(inbox, "paper/a.jpg", JPEG)
    _run(tmp_path)
    sha = _sha(JPEG)
    assert (files / "originals" / sha[:2] / f"{sha}.jpg").is_file()


def test_extension_comes_from_content(tmp_path):
    """★投入時のファイル名を信用しない。"""
    inbox, files = _paths(tmp_path)
    _put(inbox, "paper/mislabelled.png", JPEG)
    _run(tmp_path)
    sha = _sha(JPEG)
    assert (files / "originals" / sha[:2] / f"{sha}.jpg").is_file()
    assert not (files / "originals" / sha[:2] / f"{sha}.png").exists()


# ── 重複 ────────────────────────────────────────────────


def test_duplicate_within_one_run_is_skipped(tmp_path):
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/a.jpg", JPEG)
    _put(inbox, "paper/b.jpg", JPEG)
    result = _run(tmp_path)
    assert len(result.succeeded) == 1
    assert len(result.duplicates) == 1


def test_duplicate_of_existing_original_is_skipped(tmp_path):
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/a.jpg", JPEG)
    _run(tmp_path)
    _put(inbox, "paper/again.jpg", JPEG)
    result = _run(tmp_path)
    assert result.succeeded == []
    assert len(result.duplicates) == 1


def test_duplicate_is_moved_to_its_own_directory(tmp_path):
    """重複は失敗ではない。failed/ に混ぜず、専用の場所へ出す。

    inbox に残すと毎回同じものを見ることになり、黙って消すと
    「同じレシートを2回撮った」のか「別物だった」のか分からなくなる。
    """
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/a.jpg", JPEG)
    _run(tmp_path)
    again = _put(inbox, "paper/again.jpg", JPEG)
    _run(tmp_path)
    assert not again.exists()
    assert list((inbox / "duplicates").glob("*"))


# ── 失敗の扱い（第9部 §3.4）─────────────────────────────


def test_one_bad_file_does_not_stop_the_batch(tmp_path):
    """★受け入れ条件。1件壊れていても残りが処理される。"""
    inbox, _ = _paths(tmp_path)
    for i in range(5):
        _put(inbox, f"paper/ok{i}.jpg", JPEG + bytes([i]))
    _put(inbox, "paper/broken.jpg", b"not a document at all")
    result = _run(tmp_path)
    assert len(result.succeeded) == 5
    assert len(result.failed) == 1


def test_failed_file_is_kept_with_a_reason(tmp_path):
    """★黙って消さない（第9部 §7）。"""
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/broken.jpg", b"not a document")
    _run(tmp_path)
    moved = list((inbox / "failed").glob("*"))
    assert any(p.suffix != ".txt" for p in moved)
    errors = [p for p in moved if p.name.endswith(".error.txt")]
    assert errors and "判定できません" in errors[0].read_text(encoding="utf-8")


def test_failed_directory_is_not_rescanned(tmp_path):
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/broken.jpg", b"not a document")
    _run(tmp_path)
    second = _run(tmp_path)
    assert second.failed == []
    assert second.scanned == 0


def test_unsupported_type_is_rejected(tmp_path):
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/note.txt", b"plain text receipt")
    result = _run(tmp_path)
    assert len(result.failed) == 1


# ── origin の記録（第9部 §9）────────────────────────────


def test_origin_from_paper_directory_is_confident(tmp_path):
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/a.heic", HEIC)
    item = _run(tmp_path).succeeded[0]
    assert item.origin == "paper"
    assert not item.needs_review


def test_origin_from_electronic_directory_is_confident(tmp_path):
    inbox, _ = _paths(tmp_path)
    _put(inbox, "electronic/a.pdf", PDF)
    item = _run(tmp_path).succeeded[0]
    assert item.origin == "electronic"
    assert not item.needs_review


def test_file_in_inbox_root_needs_review(tmp_path):
    """★推測で確定しない。"""
    inbox, _ = _paths(tmp_path)
    _put(inbox, "loose.png", PNG)
    item = _run(tmp_path).succeeded[0]
    assert item.needs_review
    assert "確定できません" in item.origin_reason


# ── マニフェスト ────────────────────────────────────────


def test_ingestion_is_recorded_in_the_manifest(tmp_path):
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/a.jpg", JPEG)
    _run(tmp_path)
    entries = Manifest(tmp_path / "m.jsonl").entries()
    assert [e.op for e in entries] == ["add"]
    assert entries[0].sha256 == _sha(JPEG)
    assert entries[0].origin == "paper"


def test_duplicates_are_not_recorded_twice(tmp_path):
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/a.jpg", JPEG)
    _run(tmp_path)
    _put(inbox, "paper/again.jpg", JPEG)
    _run(tmp_path)
    assert len(Manifest(tmp_path / "m.jsonl").entries()) == 1


# ── dry-run ─────────────────────────────────────────────


def test_dry_run_changes_nothing(tmp_path):
    inbox, files = _paths(tmp_path)
    src = _put(inbox, "paper/a.jpg", JPEG)
    result = _run(tmp_path, dry_run=True)
    assert len(result.succeeded) == 1
    assert src.exists()
    assert not (files / "originals").exists()
    assert Manifest(tmp_path / "m.jsonl").entries() == []


# ── 走査 ────────────────────────────────────────────────


def test_empty_inbox_is_not_an_error(tmp_path):
    result = _run(tmp_path)
    assert result.scanned == 0
    assert result.succeeded == []


def test_hint_files_are_not_treated_as_documents(tmp_path):
    """第9部 §4.2 — hint は解析の手掛かりであって原本ではない。"""
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/a.jpg", JPEG)
    _put(inbox, "paper/a.jpg.hint.json", b'{"note":"x"}')
    result = _run(tmp_path)
    assert len(result.succeeded) == 1
    assert result.failed == []


def test_hint_is_carried_to_the_result(tmp_path):
    inbox, _ = _paths(tmp_path)
    _put(inbox, "paper/a.jpg", JPEG)
    _put(inbox, "paper/a.jpg.hint.json", b'{"note":"\xe4\xba\xa4\xe9\x80\x9a\xe8\xb2\xbb"}')
    item = _run(tmp_path).succeeded[0]
    assert item.hint == {"note": "交通費"}


def test_results_are_ordered_deterministically(tmp_path):
    inbox, _ = _paths(tmp_path)
    for name in ("c.jpg", "a.jpg", "b.jpg"):
        _put(inbox, f"paper/{name}", JPEG + name.encode())
    names = [i.source_name for i in _run(tmp_path).succeeded]
    assert names == sorted(names)
