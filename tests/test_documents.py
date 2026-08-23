"""documents/*.json の読み込み（第1部 §6・§7）。"""

from __future__ import annotations

import json

import pytest

from shiwake.ledger.documents import load_month, load_skipped

# ── 領収書ごとの科目指定（lines[].account）─────────────
#
# ★店名だけで決まらない店（ダイソー、ヤマト運輸、タクシー）は、
#   領収書の側で科目を指定する。categories.yaml にその旨が
#   書いてあるのに、読む側が実装されていなかった。
#   **指定が黙って無視されると、私用と事業が混ざったまま通る。**


def _receipt_doc(lines, **over):
    doc = {
        "schema_version": 1,
        "doc_id": "doc_2026-04-25_x_a1b2c3",
        "type": "receipt",
        "source": {
            "original_ref": "sha256:" + "ab" * 32,
            "original_ext": "jpg",
            "ingested_at": "2026-04-26T10:00:00+09:00",
            "extractor": {"skill": "s", "skill_version": "1", "model": "m"},
        },
        "origin": "paper",
        "paper_retained": True,
        "needs_review": False,
        "review_reason": None,
        "issuer": {"name": "サンプル運輸"},
        "issued_at": "2026-04-25T10:02:00+09:00",
        "currency": "JPY",
        "total": sum(line["amount"] or 0 for line in lines),
        "tax_breakdown": [],
        "payment": {"method": "cash"},
        "lines": lines,
    }
    doc.update(over)
    return doc


def _write(tmp_path, doc):
    d = tmp_path / "2026" / "04"
    d.mkdir(parents=True)
    (d / f"{doc['doc_id']}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_line_account_becomes_the_receipt_account(tmp_path):
    root = _write(
        tmp_path,
        _receipt_doc(
            [{"description": "宅急便", "amount": 940, "account": "Expenses:Business:Postage"}]
        ),
    )
    _receipts, _lines, accounts = load_month(root, "2026-04")
    assert accounts["doc_2026-04-25_x_a1b2c3"] == "Expenses:Business:Postage"


def test_receipt_without_line_accounts_has_no_override(tmp_path):
    root = _write(tmp_path, _receipt_doc([{"description": "宅急便", "amount": 940}]))
    _receipts, _lines, accounts = load_month(root, "2026-04")
    assert "doc_2026-04-25_x_a1b2c3" not in accounts


def test_mixed_line_accounts_are_reported_not_silently_merged(tmp_path):
    """★1枚の領収書が事業と私用にまたがることがある。

    黙って片方に寄せると、寄せた側が丸ごと間違う。
    まだ分割に対応していないので、気づけるように残す。
    """
    root = _write(
        tmp_path,
        _receipt_doc(
            [
                {"description": "部品", "amount": 500, "account": "Expenses:Business:Supplies"},
                {
                    "description": "菓子",
                    "amount": 300,
                    "account": "Expenses:Personal:Food:Groceries",
                },
            ]
        ),
    )
    with pytest.raises(ValueError, match="doc_2026-04-25_x_a1b2c3"):
        load_month(root, "2026-04")


# ── 金額が読めなかった領収書 ────────────────────────────


def test_receipt_with_no_total_is_not_loaded_as_zero(tmp_path):
    """★合計が読めなかった領収書を 0円 として元帳に入れない。

    `total or 0` になっていて、null が 0 になっていた。
    貸借は合うので bean-check も通り、**費用が黙って過小になる**。
    読めなかったものは元帳に入れず、その旨を報せる。
    """
    doc = _receipt_doc([{"description": "不明", "amount": None}])
    doc["total"] = None
    doc["needs_review"] = True
    doc["review_reason"] = "下端が写っておらず合計が読めない"
    root = _write(tmp_path, doc)
    receipts, _lines, _accounts = load_month(root, "2026-04")
    assert receipts == []


def test_unreadable_receipt_is_reported(tmp_path):
    """黙って消えるのも困る。除いたことが分かるようにする。"""
    doc = _receipt_doc([{"description": "不明", "amount": None}])
    doc["total"] = None
    doc["needs_review"] = True
    doc["review_reason"] = "下端が写っておらず合計が読めない"
    root = _write(tmp_path, doc)
    assert load_skipped(root, "2026-04") == ["doc_2026-04-25_x_a1b2c3"]


def test_a_genuinely_zero_yen_receipt_is_kept(tmp_path):
    """0円の領収書は実在する（全額値引きなど）。null と混同しない。"""
    doc = _receipt_doc([{"description": "値引き後", "amount": 0}])
    root = _write(tmp_path, doc)
    receipts, _lines, _accounts = load_month(root, "2026-04")
    assert len(receipts) == 1
    assert receipts[0].total == 0
