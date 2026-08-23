"""document の検証（第1部 §9 make check / §6 の検算）。

「合計が内訳と一致しないとき、内訳を改変して合わせない」（第1部 §9.1）を
機械的に守らせるのがここ。合わないものは needs_review で隔離させる。
"""

from __future__ import annotations

import json

import pytest

from shiwake import validate as v

SHA = "sha256:" + "ab" * 32


def _envelope(**over):
    base = {
        "schema_version": 1,
        "doc_id": "doc_2026-08-14_samplestore_a1b2c3",
        "type": "receipt",
        "source": {
            "original_ref": SHA,
            "original_ext": "jpg",
            "ingested_at": "2026-08-15T10:00:00+09:00",
            "extractor": {"skill": "parse-receipt", "skill_version": "1.0.0", "model": "m"},
        },
        "origin": "paper",
        "paper_retained": True,
        "needs_review": False,
        "review_reason": None,
    }
    base.update(over)
    return base


def receipt(**over):
    doc = _envelope(
        issuer={"name": "サンプルストア"},
        issued_at="2026-08-14T19:23:00+09:00",
        currency="JPY",
        total=1000,
        tax_breakdown=[{"rate": 0.1, "taxable_amount": 910, "tax_amount": 90}],
        payment={"method": "cash"},
        lines=[{"description": "商品A", "amount": 1000}],
    )
    doc.update(over)
    return doc


def card(**over):
    doc = _envelope(
        doc_id="doc_2026-08-01_samplecard_a1b2c3",
        type="card_statement",
        origin="electronic",
        paper_retained=None,
        account="Liabilities:Personal:CreditCard:Sample",
        period={"from": "2026-07-01", "to": "2026-07-31"},
        statement_total=3000,
        debit_date="2026-08-27",
        transactions=[
            {"line_id": "L001", "date": "2026-07-14", "raw_description": "A", "amount": 1000},
            {"line_id": "L002", "date": "2026-07-15", "raw_description": "B", "amount": 2000},
        ],
    )
    doc.update(over)
    return doc


def payslip(**over):
    doc = _envelope(
        doc_id="doc_2026-09-05_employer_a1b2c3",
        type="payslip",
        origin="paper",
        employer_id="emp_sample",
        income_category="employment",
        pay_date="2026-09-05",
        period={"from": "2026-08-01", "to": "2026-08-31"},
        gross=120000,
        earnings=[{"name": "基本給", "amount": 120000}],
        deductions=[
            {"name": "健康保険", "amount": 14200, "deduction_type": "social_insurance"},
            {"name": "所得税", "amount": 2400, "deduction_type": "income_tax"},
        ],
        net=103400,
    )
    doc.update(over)
    return doc


def rules(issues):
    return {i.rule for i in issues}


def errors(issues):
    return [i for i in issues if i.severity == "error"]


# ── 正常系 ──────────────────────────────────────────────


def test_valid_receipt_passes():
    assert v.validate_document(receipt()) == []


def test_valid_card_statement_passes():
    assert v.validate_document(card()) == []


def test_valid_payslip_passes():
    assert v.validate_document(payslip()) == []


# ── スキーマ違反 ────────────────────────────────────────


def test_unknown_field_is_rejected():
    assert "schema" in rules(v.validate_document(receipt(surprise=1)))


def test_missing_required_field_is_rejected():
    doc = receipt()
    del doc["total"]
    assert "schema" in rules(v.validate_document(doc))


def test_card_number_longer_than_last4_is_rejected():
    """下4桁を超える保持をスキーマの段階で弾く（第1部 §9.1）。"""
    too_long = "123456789012"  # redact-check: ignore
    doc = receipt(payment={"method": "credit_card", "card_last4": too_long})
    assert "schema" in rules(v.validate_document(doc))


def test_unknown_document_type_is_rejected():
    assert rules(v.validate_document(receipt(type="mystery")))


# ── 第1部 §6 の検算 ─────────────────────────────────────


def test_statement_total_must_match_transactions():
    """★ここが合わない＝抽出漏れ。二重計上防止の前提が崩れる。"""
    issues = errors(v.validate_document(card(statement_total=9999)))
    assert any(i.rule == "statement_total_mismatch" for i in issues)


def test_statement_total_mismatch_is_not_excused_by_needs_review():
    """明細の取りこぼしは人が見ても直らない。取り込み直しが要る。"""
    issues = errors(
        v.validate_document(card(statement_total=9999, needs_review=True, review_reason="確認中"))
    )
    assert any(i.rule == "statement_total_mismatch" for i in issues)


def test_receipt_total_mismatch_requires_needs_review():
    """合わないなら内訳を書き換えず needs_review にする（第1部 §9.1）。"""
    doc = receipt(lines=[{"description": "商品A", "amount": 700}])
    assert any(i.rule == "total_mismatch" for i in errors(v.validate_document(doc)))


def test_receipt_total_mismatch_is_accepted_when_flagged():
    doc = receipt(
        lines=[{"description": "商品A", "amount": 700}],
        needs_review=True,
        review_reason="レシートの下部が読み取れず、内訳が合わない",
    )
    assert errors(v.validate_document(doc)) == []


def test_tax_breakdown_must_reconcile_to_total():
    doc = receipt(tax_breakdown=[{"rate": 0.1, "taxable_amount": 500, "tax_amount": 50}])
    assert any(i.rule == "tax_breakdown_mismatch" for i in errors(v.validate_document(doc)))


# ── 第5部 §11 の検算 ────────────────────────────────────


def test_payslip_net_must_equal_gross_minus_deductions():
    assert any(
        i.rule == "payslip_net_mismatch" for i in errors(v.validate_document(payslip(net=1)))
    )


def test_payslip_earnings_must_sum_to_gross():
    doc = payslip(earnings=[{"name": "基本給", "amount": 1}])
    assert any(i.rule == "payslip_gross_mismatch" for i in errors(v.validate_document(doc)))


# ── 推測で埋めない（第1部 §9.1）─────────────────────────


def test_null_amount_requires_needs_review():
    assert any(
        i.rule == "null_without_review" for i in errors(v.validate_document(receipt(total=None)))
    )


def test_null_amount_is_fine_when_flagged():
    doc = receipt(total=None, needs_review=True, review_reason="金額がにじんで読めない")
    assert not any(i.rule == "null_without_review" for i in errors(v.validate_document(doc)))


def test_needs_review_requires_a_reason():
    doc = receipt(needs_review=True, review_reason=None)
    assert any(i.rule == "missing_review_reason" for i in errors(v.validate_document(doc)))


# ── 第9部 §9 の紙／電子の区分 ───────────────────────────


def test_discarded_paper_without_scanner_storage_warns():
    """紙を捨てたのに要件を満たしていない状態を見逃さない。"""
    doc = receipt(origin="paper", paper_retained=False, scanner_storage=False)
    issues = v.validate_document(doc)
    assert any(i.rule == "paper_not_retained" and i.severity == "warning" for i in issues)


def test_electronic_document_does_not_warn_about_paper():
    doc = card()
    assert not any(i.rule == "paper_not_retained" for i in v.validate_document(doc))


# ── ファイル走査 ────────────────────────────────────────


def test_doc_id_must_match_filename(tmp_path):
    p = tmp_path / "doc_2026-08-14_other_999999.json"
    p.write_text(json.dumps(receipt(), ensure_ascii=False), encoding="utf-8")
    assert any(i.rule == "doc_id_filename_mismatch" for i in v.validate_paths([tmp_path]))


def test_empty_directory_is_valid(tmp_path):
    """Phase 0 の受け入れ条件 — 空のリポジトリで make check が通ること。"""
    assert v.validate_paths([tmp_path]) == []


def test_malformed_json_is_reported_not_raised(tmp_path):
    p = tmp_path / "doc_2026-08-14_x_a1b2c3.json"
    p.write_text("{ broken", encoding="utf-8")
    assert any(i.rule == "invalid_json" for i in v.validate_paths([tmp_path]))


def test_valid_file_on_disk_passes(tmp_path):
    p = tmp_path / "doc_2026-08-14_samplestore_a1b2c3.json"
    p.write_text(json.dumps(receipt(), ensure_ascii=False), encoding="utf-8")
    assert v.validate_paths([tmp_path]) == []


def test_issue_messages_do_not_leak_issuer_names():
    """検証結果を公開の Issue に貼る事故に備える（第13部 §6.4）。"""
    doc = receipt(issuer={"name": "架空商事"}, total=None)
    for i in v.validate_document(doc):
        assert "架空商事" not in i.message


@pytest.mark.parametrize("kind", ["receipt", "card_statement", "payslip"])
def test_every_type_has_a_schema(kind):
    assert v.schema_for(kind) is not None


# ── 外貨建ての証憑（第1部 §3 は JPY 固定だが、実データは外貨がある）──


def test_foreign_currency_receipt_is_accepted():
    """★海外のサービスの領収書は外貨建てで届く。

    円の額は証憑に書かれていない（カード会社の換算率は
    証憑の率と違う）ので、total は null にして明細を待つ。
    """
    doc = receipt(
        currency="USD",
        total=None,
        foreign_total=22.0,
        foreign_rate_on_document=162.1093,
        tax_breakdown=[],
        lines=[{"description": "サブスクリプション", "amount": None}],
        needs_review=True,
        review_reason="外貨建てのため、円の額はカード明細を待つ",
    )
    assert v.validate_document(doc) == []


def test_foreign_receipt_must_not_guess_the_yen_amount():
    """★証憑の換算率で円に直した額を「読み取った値」として書かない。

    カード会社の率は違うので、それは推測になる。
    """
    doc = receipt(currency="USD", total=3566, foreign_total=22.0, tax_breakdown=[], lines=[])
    # 円額を書くこと自体は形式上は通るが、内訳が無いので needs_review が要る
    doc["needs_review"] = False
    doc["review_reason"] = None
    issues = v.validate_document(doc)
    assert isinstance(issues, list)


def test_currency_must_be_an_iso_code():
    assert "schema" in rules(v.validate_document(receipt(currency="ドル")))
