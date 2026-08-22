"""領収書とカード明細行の突合（第1部 §6）。

★このシステムの心臓部。同じ支出が2つの証憑に現れるので、
  ここを間違えると集計が全部壊れる。
"""

from __future__ import annotations

from datetime import date

from shiwake.ledger.merchants import Merchant, MerchantIndex
from shiwake.ledger.reconcile import (
    CardLine,
    Links,
    Receipt,
    confirm,
    find_candidates,
    load_links,
    save_links,
)

INDEX = MerchantIndex(
    [
        Merchant(id="store", canonical="サンプルストア", aliases=("サンプルストア ワタダ",)),
        Merchant(id="denki", canonical="サンプル電機"),
    ]
)


def receipt(
    doc_id="doc_r1", d=(2026, 7, 14), issuer="サンプルストア", total=1234, method="credit_card"
):
    return Receipt(doc_id=doc_id, date=date(*d), issuer=issuer, total=total, payment_method=method)


def card_line(line_id="L001", d=(2026, 7, 14), desc="サンプルストア ワタダ", amount=1234):
    return CardLine(
        statement_doc_id="doc_stmt",
        account="Liabilities:Personal:CreditCard:Sample",
        line_id=line_id,
        date=date(*d),
        description=desc,
        amount=amount,
    )


# ── 一致条件（第1部 §6）─────────────────────────────────


def test_exact_match_is_confident():
    r = find_candidates([receipt()], [card_line()], INDEX)
    assert len(r.confident) == 1
    assert r.confident[0].card_line_key == "doc_stmt:L001"


def test_amount_must_match_exactly():
    """★金額は完全一致。1円でも違えば別の取引。"""
    r = find_candidates([receipt(total=1234)], [card_line(amount=1235)], INDEX)
    assert r.confident == []
    assert r.unmatched_receipts == ["doc_r1"]


def test_date_within_three_days_matches():
    r = find_candidates([receipt(d=(2026, 7, 14))], [card_line(d=(2026, 7, 17))], INDEX)
    assert len(r.confident) == 1


def test_date_beyond_three_days_does_not_match():
    r = find_candidates([receipt(d=(2026, 7, 14))], [card_line(d=(2026, 7, 18))], INDEX)
    assert r.confident == []


def test_dictionary_bridges_the_notation_gap():
    """★カタカナの明細と漢字の領収書。実務で必ず起きる。"""
    r = find_candidates(
        [receipt(issuer="サンプルストア 和多田店")],
        [card_line(desc="サンプルストア ワタダ")],
        MerchantIndex(
            [
                Merchant(
                    id="store",
                    canonical="サンプルストア",
                    aliases=("サンプルストア ワタダ", "サンプルストア 和多田店"),
                )
            ]
        ),
    )
    assert len(r.confident) == 1


def test_different_merchant_does_not_match():
    r = find_candidates(
        [receipt(issuer="サンプル電機")], [card_line(desc="サンプルストア ワタダ")], INDEX
    )
    assert r.confident == []


# ── 自動確定しない（第1部 §6）───────────────────────────


def test_multiple_candidates_are_not_auto_confirmed():
    """★同じ日に同じ店で同じ額を2回使うことは普通にある。

    どちらが正しいかは機械には決められない。人間に投げる。
    """
    lines = [card_line(line_id="L001"), card_line(line_id="L002")]
    r = find_candidates([receipt()], lines, INDEX)
    assert r.confident == []
    assert "doc_r1" in r.ambiguous
    assert len(r.ambiguous["doc_r1"]) == 2


def test_ambiguous_candidates_are_ordered_by_confidence():
    lines = [
        card_line(line_id="L001", d=(2026, 7, 17)),
        card_line(line_id="L002", d=(2026, 7, 14)),
    ]
    r = find_candidates([receipt(d=(2026, 7, 14))], lines, INDEX)
    assert [c.card_line_key for c in r.ambiguous["doc_r1"]] == ["doc_stmt:L002", "doc_stmt:L001"]


def test_ambiguous_lines_are_not_reported_as_unmatched():
    lines = [card_line(line_id="L001"), card_line(line_id="L002")]
    r = find_candidates([receipt()], lines, INDEX)
    assert r.unmatched_card_lines == []


# ── 未突合の把握 ────────────────────────────────────────


def test_card_line_without_receipt_is_reported():
    r = find_candidates([], [card_line()], INDEX)
    assert r.unmatched_card_lines == ["doc_stmt:L001"]


def test_receipt_without_card_line_is_reported():
    r = find_candidates([receipt()], [], INDEX)
    assert r.unmatched_receipts == ["doc_r1"]


def test_already_linked_items_are_skipped():
    """★再実行しても壊れない。確定済みを作り直さない。"""
    r = find_candidates(
        [receipt()], [card_line()], INDEX, already_linked={"doc_r1", "doc_stmt:L001"}
    )
    assert r.confident == []
    assert r.unmatched_receipts == []
    assert r.unmatched_card_lines == []


def test_one_card_line_is_never_claimed_by_two_receipts():
    """★二重計上そのもの。1行の明細を2枚の領収書が確定で掴んではいけない。

    同じ日に同じ店で同じ額を2回使い、レシートが2枚ある場合に起きる。
    どちらがどの行かは機械には決められないので、両方とも人間に投げる。
    """
    receipts = [receipt(doc_id="doc_a"), receipt(doc_id="doc_b")]
    r = find_candidates(receipts, [card_line()], INDEX)
    assert r.confident == []
    assert set(r.ambiguous) == {"doc_a", "doc_b"}


def test_confident_links_never_share_a_card_line():
    """確定したリンクの中に、同じ明細行を指すものが2つ以上ない。"""
    receipts = [
        receipt(doc_id="doc_a", total=1000),
        receipt(doc_id="doc_b", total=2000),
        receipt(doc_id="doc_c", total=1000),
    ]
    lines = [
        card_line(line_id="L001", amount=1000),
        card_line(line_id="L002", amount=2000),
    ]
    r = find_candidates(receipts, lines, INDEX)
    keys = [c.card_line_key for c in r.confident]
    assert len(keys) == len(set(keys))


# ── 永続化 ──────────────────────────────────────────────


def test_links_round_trip(tmp_path):
    path = tmp_path / "2026-07.json"
    save_links(path, Links(month="2026-07", links={"doc_r1": "doc_stmt:L001"}))
    loaded = load_links(path)
    assert loaded.month == "2026-07"
    assert loaded.card_line_for("doc_r1") == "doc_stmt:L001"
    assert loaded.doc_for_card_line("doc_stmt:L001") == "doc_r1"


def test_missing_links_file_is_empty(tmp_path):
    assert load_links(tmp_path / "2026-07.json").links == {}


def test_confirm_does_not_overwrite_existing_links():
    """★人が確定したものを、後の自動処理で上書きしない。"""
    existing = Links(month="2026-07", links={"doc_r1": "doc_stmt:L009"})
    from shiwake.ledger.reconcile import Candidate

    merged = confirm(existing, [Candidate("doc_r1", "doc_stmt:L001", 1.0, 0)])
    assert merged.links["doc_r1"] == "doc_stmt:L009"


def test_linked_keys_covers_both_sides():
    links = Links(month="2026-07", links={"doc_r1": "doc_stmt:L001"})
    assert links.linked_keys() == {"doc_r1", "doc_stmt:L001"}


def test_saved_links_are_stable(tmp_path):
    """並び順が安定しないと、差分レビューが無意味になる。"""
    path = tmp_path / "2026-07.json"
    links = Links(month="2026-07", links={"doc_z": "doc_stmt:L002", "doc_a": "doc_stmt:L001"})
    save_links(path, links)
    first = path.read_text(encoding="utf-8")
    save_links(path, load_links(path))
    assert path.read_text(encoding="utf-8") == first
    assert first.index("doc_a") < first.index("doc_z")
