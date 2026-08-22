"""Agent Skill が満たすべき形（第1部 §9.2 / 第13部 §3.5）。

Skill は人が読む文書だが、要件があるので機械で確かめられる部分は確かめる。
特に「例示に実在の店名を書かない」は、公開リポジトリでは事故に直結する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))

EXPECTED = {"parse-receipt", "parse-card-statement", "parse-payslip"}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_three_skills_exist():
    assert {p.parent.name for p in SKILLS} == EXPECTED


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_has_frontmatter_with_name_and_description(skill):
    text = _text(skill)
    assert text.startswith("---\n")
    head = text.split("---", 2)[1]
    assert "name:" in head and "description:" in head


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_name_matches_the_directory(skill):
    head = _text(skill).split("---", 2)[1]
    lines = head.splitlines()
    name = next(ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("name:"))
    assert name == skill.parent.name


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_has_at_least_three_good_and_bad_pairs(skill):
    """第1部 §9.2 — Few-shot が精度に効くので、例を3組以上入れる。"""
    text = _text(skill)
    assert text.count("**良い**") >= 3, "良い例が3組未満です"
    assert text.count("**悪い**") >= 3, "悪い例が3組未満です"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_forbids_guessing(skill):
    """「推測で埋めない」が明記されていること（第1部 §9.1）。"""
    text = _text(skill)
    assert "推測" in text
    assert "needs_review" in text


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_example_merchants_are_fictional(skill):
    """★実在の店名・取引先を例示に使わない（第13部 §3.5 経路13）。"""
    text = _text(skill)
    assert "サンプル" in text or "架空" in text


def test_payslip_skill_leads_with_masking():
    """給与明細はマスク処理が最優先（第1部 §11 S3）。"""
    text = _text(ROOT / "skills" / "parse-payslip" / "SKILL.md")
    body = text.split("---", 2)[2]
    masking = body.index("書いてはいけないもの")
    output = body.index("## 出力")
    assert masking < output, "マスクの説明が出力形式より後にあります"
    assert "マイナンバー" in body


def test_payslip_skill_states_salary_is_not_business_income():
    """給与を事業の損益に入れない（第5部 §1）。"""
    text = _text(ROOT / "skills" / "parse-payslip" / "SKILL.md")
    assert "事業所得ではない" in text
    assert "employment" in text


def test_card_skill_requires_self_verification():
    """請求総額と明細の合計の検算（第1部 §6）。"""
    text = _text(ROOT / "skills" / "parse-card-statement" / "SKILL.md")
    assert "検算" in text
    assert "一致" in text


def test_skills_tell_the_model_to_read_derivatives_not_originals():
    """原本のバイト列を触らせない（第9部 §1.2）。"""
    text = _text(ROOT / "skills" / "parse-receipt" / "SKILL.md")
    assert "派生" in text
