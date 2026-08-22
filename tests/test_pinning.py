"""依存のピンの検査（第13部 §4・§12）。"""

from __future__ import annotations

import textwrap

import pytest

from shiwake.safety.pinning import check_pins

REPO = "git+https://example.com/app"


def write(tmp_path, dependencies: str, extra: str = ""):
    p = tmp_path / "pyproject.toml"
    p.write_text(
        textwrap.dedent(f"""
            [project]
            name = "data"
            version = "0"
            dependencies = [{dependencies}]
            {extra}
        """),
        encoding="utf-8",
    )
    return p


def test_tag_pin_is_accepted(tmp_path):
    assert check_pins(write(tmp_path, f'"shiwake @ {REPO}@v0.1.0"')) == []


def test_version_pin_is_accepted(tmp_path):
    assert check_pins(write(tmp_path, '"shiwake==0.1.0"')) == []


def test_commit_pin_is_accepted(tmp_path):
    assert check_pins(write(tmp_path, f'"shiwake @ {REPO}@{"a" * 40}"')) == []


@pytest.mark.parametrize("branch", ["main", "master", "HEAD"])
def test_branch_tracking_is_rejected(tmp_path, branch):
    """★これが本体。追従させると帳簿の計算が黙って変わる。"""
    problems = check_pins(write(tmp_path, f'"shiwake @ {REPO}@{branch}"'))
    assert problems and "黙って変わります" in problems[0].message


def test_lower_bound_only_is_rejected(tmp_path):
    problems = check_pins(write(tmp_path, '"shiwake>=0.1.0"'))
    assert problems


def test_missing_dependency_is_reported(tmp_path):
    problems = check_pins(write(tmp_path, '"pyyaml==6.0"'))
    assert problems and "宣言されていません" in problems[0].message


def test_local_path_source_is_rejected(tmp_path):
    """★手元では動くが、他のマシンでは解決できない。"""
    extra = '[tool.uv.sources]\nshiwake = { path = "../shiwake", editable = true }'
    problems = check_pins(write(tmp_path, f'"shiwake @ {REPO}@v0.1.0"', extra))
    assert problems and "他のマシンでは解決できません" in problems[0].message


def test_missing_file_is_reported(tmp_path):
    assert check_pins(tmp_path / "absent.toml")
