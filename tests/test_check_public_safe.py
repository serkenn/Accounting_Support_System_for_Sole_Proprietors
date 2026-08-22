"""公開リポジトリの安全性検査のテスト（第13部 §6.2）。"""

from __future__ import annotations

import textwrap

from conftest import fake_bank_account

from shiwake.safety import Denylist
from shiwake.safety import public_safe as ps


def _repo(tmp_path):
    (tmp_path / "src").mkdir()
    return tmp_path


# ── 置いてはいけないファイル ─────────────────────────────


def test_env_file_is_rejected(tmp_path):
    root = _repo(tmp_path)
    (root / ".env").write_text("TOKEN=x", encoding="utf-8")
    assert any(p.kind == "forbidden_file" for p in ps.check_forbidden_files(root))


def test_compose_file_is_rejected(tmp_path):
    """自宅の構成が漏れる（第13部 §7 インフラ）。"""
    root = _repo(tmp_path)
    (root / "compose.yaml").write_text("services: {}", encoding="utf-8")
    assert any(p.kind == "forbidden_file" for p in ps.check_forbidden_files(root))


def test_timestamp_token_is_rejected(tmp_path):
    root = _repo(tmp_path)
    (root / "a.tsr").write_bytes(b"\x30\x82")
    assert any(p.kind == "forbidden_file" for p in ps.check_forbidden_files(root))


def test_ordinary_files_are_accepted(tmp_path):
    root = _repo(tmp_path)
    (root / "README.md").write_text("hello", encoding="utf-8")
    assert ps.check_forbidden_files(root) == []


# ── フィクスチャは合成データのみ ─────────────────────────


def test_text_fixture_without_marker_is_rejected(tmp_path):
    root = _repo(tmp_path)
    (root / "fixtures").mkdir()
    (root / "fixtures" / "receipt.json").write_text('{"total": 100}', encoding="utf-8")
    assert any(p.kind == "fixture_not_synthetic" for p in ps.check_fixtures_are_synthetic(root))


def test_text_fixture_with_marker_is_accepted(tmp_path):
    root = _repo(tmp_path)
    (root / "fixtures").mkdir()
    (root / "fixtures" / "receipt.json").write_text(
        '{"_note": "SYNTHETIC", "total": 100}', encoding="utf-8"
    )
    assert ps.check_fixtures_are_synthetic(root) == []


def test_binary_fixture_must_be_declared_in_manifest(tmp_path):
    root = _repo(tmp_path)
    (root / "fixtures").mkdir()
    (root / "fixtures" / "receipt.jpg").write_bytes(b"\xff\xd8\xff")
    assert any(p.kind == "fixture_unlisted" for p in ps.check_fixtures_are_synthetic(root))


def test_declared_binary_fixture_needs_provenance(tmp_path):
    root = _repo(tmp_path)
    (root / "fixtures").mkdir()
    (root / "fixtures" / "receipt.jpg").write_bytes(b"\xff\xd8\xff")
    (root / "fixtures" / "MANIFEST.yaml").write_text(
        "files:\n  - path: receipt.jpg\n    synthetic: true\n", encoding="utf-8"
    )
    problems = ps.check_fixtures_are_synthetic(root)
    assert any(p.kind == "fixture_no_provenance" for p in problems)


def test_fully_declared_binary_fixture_is_accepted(tmp_path):
    root = _repo(tmp_path)
    (root / "fixtures").mkdir()
    (root / "fixtures" / "receipt.jpg").write_bytes(b"\xff\xd8\xff")
    (root / "fixtures" / "MANIFEST.yaml").write_text(
        "files:\n  - path: receipt.jpg\n    synthetic: true\n"
        "    how_made: 架空のレシートを作成して撮影\n",
        encoding="utf-8",
    )
    assert ps.check_fixtures_are_synthetic(root) == []


# ── 税務テンプレートに値を入れない（第13部 §8）──────────


def test_tax_template_with_a_value_is_rejected(tmp_path):
    root = _repo(tmp_path)
    (root / "templates" / "tax").mkdir(parents=True)
    (root / "templates" / "tax" / "YYYY.yaml").write_text(
        "basic_deduction: 480000\n", encoding="utf-8"
    )
    problems = ps.check_tax_templates_are_null(root)
    assert any(p.kind == "tax_template_not_null" for p in problems)


def test_tax_template_with_all_nulls_is_accepted(tmp_path):
    root = _repo(tmp_path)
    (root / "templates" / "tax").mkdir(parents=True)
    (root / "templates" / "tax" / "YYYY.yaml").write_text(
        textwrap.dedent(
            """
            basic_deduction: null
            thresholds:
              dependent_relative_limit: null
              working_student_limit: null
            """
        ),
        encoding="utf-8",
    )
    assert ps.check_tax_templates_are_null(root) == []


def test_nested_value_in_tax_template_is_rejected(tmp_path):
    root = _repo(tmp_path)
    (root / "templates" / "tax").mkdir(parents=True)
    (root / "templates" / "tax" / "YYYY.yaml").write_text(
        "thresholds:\n  working_student_limit: 850000\n", encoding="utf-8"
    )
    assert ps.check_tax_templates_are_null(root) != []


# ── パターン検査は strict で走る ────────────────────────


def test_account_number_in_source_is_caught(tmp_path):
    """Phase 0.5 の受け入れ条件そのもの。"""
    root = _repo(tmp_path)
    (root / "src" / "leak.py").write_text(
        f'BANK = {{"account_no": "{fake_bank_account()}"}}\n', encoding="utf-8"
    )
    findings = ps.check_patterns(root)
    assert any(f.rule == "bank_account" and f.severity == "error" for f in findings)


def test_clean_source_passes(tmp_path):
    root = _repo(tmp_path)
    source = "TOTAL = 1234567\n"  # redact-check: ignore
    (root / "src" / "ok.py").write_text(source, encoding="utf-8")
    assert ps.check_patterns(root) == []


def test_denylist_is_applied_when_injected(tmp_path):
    """名前ベースの検査は非公開側から注入される（第13部 §3.7）。"""
    root = _repo(tmp_path)
    (root / "src" / "x.py").write_text('EXPORTER = "架空商事"\n', encoding="utf-8")
    findings = ps.check_patterns(root, Denylist(["架空商事"]))
    assert any(f.rule == "denylist" for f in findings)


def test_explanatory_notes_are_allowed_in_tax_templates(tmp_path):
    """注記は null にできない。ここを弾くとテンプレートに説明が書けなくなる。"""
    root = _repo(tmp_path)
    (root / "templates" / "tax").mkdir(parents=True)
    (root / "templates" / "tax" / "YYYY.yaml").write_text(
        textwrap.dedent(
            """
            thresholds:
              working_student_limit: null
              social_insurance_note: 社会保険の加入基準は税制とは別です
            """
        ),
        encoding="utf-8",
    )
    assert ps.check_tax_templates_are_null(root) == []


def test_note_key_does_not_hide_a_real_value(tmp_path):
    """注記の免除が、値を隠す抜け道にならないこと。"""
    root = _repo(tmp_path)
    (root / "templates" / "tax").mkdir(parents=True)
    (root / "templates" / "tax" / "YYYY.yaml").write_text(
        "deductions:\n  basic_deduction: 480000\n  basic_deduction_note: 参考\n",
        encoding="utf-8",
    )
    assert ps.check_tax_templates_are_null(root) != []
