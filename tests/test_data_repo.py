"""データリポジトリにアプリのコードが混ざらないこと（第13部 §0）。"""

from __future__ import annotations

from shiwake.safety.data_repo import check_no_app_code


def test_clean_data_repo_passes(tmp_path):
    (tmp_path / "documents").mkdir()
    (tmp_path / "documents" / "doc.json").write_text("{}", encoding="utf-8")
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "accounts.yaml").write_text("version: 1", encoding="utf-8")
    assert check_no_app_code(tmp_path) == []


def test_package_directory_is_rejected(tmp_path):
    """★作業ディレクトリを間違えるだけで起きる。人の注意力では防げない。"""
    (tmp_path / "src" / "shiwake").mkdir(parents=True)
    (tmp_path / "src" / "shiwake" / "magic.py").write_text("x = 1", encoding="utf-8")
    problems = check_no_app_code(tmp_path)
    assert problems and "第13部" in problems[0].message


def test_stray_python_file_is_rejected(tmp_path):
    (tmp_path / "helper.py").write_text("x = 1", encoding="utf-8")
    assert check_no_app_code(tmp_path) != []


def test_config_files_are_not_code(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
    (tmp_path / "Makefile").write_text("check:", encoding="utf-8")
    assert check_no_app_code(tmp_path) == []


def test_hooks_are_allowed_when_declared(tmp_path):
    (tmp_path / ".githooks").mkdir()
    (tmp_path / ".githooks" / "helper.py").write_text("x = 1", encoding="utf-8")
    assert check_no_app_code(tmp_path, allow=[".githooks"]) == []


def test_virtualenv_is_ignored(tmp_path):
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "mod.py").write_text("x = 1", encoding="utf-8")
    assert check_no_app_code(tmp_path) == []
