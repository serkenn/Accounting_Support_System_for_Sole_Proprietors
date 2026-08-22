"""店名の正規化と一致判定（第1部 §6）。"""

from __future__ import annotations

import textwrap

import pytest

from shiwake.ledger.merchants import Merchant, MerchantIndex, load_merchants, normalize, similarity

# ── 正規化 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("サンプルストア", "ｻﾝﾌﾟﾙｽﾄｱ"),  # 全角半角カナ
        ("Sample Store", "SAMPLE  STORE"),  # 大小文字と空白
        ("サンプル商店", "株式会社サンプル商店"),  # 法人格
        ("サンプル・ストア", "サンプルストア"),  # 中黒
        ("ＡＢＣ商店", "ABC商店"),  # 全角英数
    ],
)
def test_variants_normalize_to_the_same_string(left, right):
    assert normalize(left) == normalize(right)


def test_different_names_do_not_collide():
    assert normalize("サンプルストア") != normalize("サンプル電機")


# ── 類似度 ──────────────────────────────────────────────


def test_identical_names_score_one():
    assert similarity("サンプルストア", "サンプルストア") == 1.0


def test_branch_suffix_scores_high():
    """支店名の有無は同じ店であることが多い。"""
    assert similarity("サンプルストア", "サンプルストア北店") >= 0.6


def test_unrelated_names_score_low():
    assert similarity("サンプルストア", "架空フーズ") < 0.6


def test_shared_prefix_can_cross_the_threshold():
    """★仕様の閾値 0.6 の弱点を記録しておく。

    共通の接頭辞を持つ別の店は、閾値を超えることがある。
    ここが誤って一致しても致命的にならないのは、突合が
    **金額の完全一致と日付差3日以内も同時に要求する**ため。
    店名だけでリンクを作らない設計がこれを吸収している。

    別名辞書に両方を登録すれば 0.0 に落ちる（辞書が主、類似度は補助）。
    """
    assert similarity("サンプルストア", "サンプル電機") >= 0.6
    index = MerchantIndex(
        [
            Merchant(id="a", canonical="サンプルストア"),
            Merchant(id="b", canonical="サンプル電機"),
        ]
    )
    assert index.match_score("サンプルストア", "サンプル電機") == 0.0


def test_empty_name_scores_zero():
    assert similarity("", "サンプルストア") == 0.0


# ── 別名辞書 ────────────────────────────────────────────

RULES = textwrap.dedent(
    """
    version: 1
    merchants:
      - id: sample_store
        canonical: サンプルストア
        aliases:
          - サンプルストア ワタダ
          - サンプルストア 和多田店
      - id: sample_denki
        canonical: サンプル電機
    """
)


@pytest.fixture
def index(tmp_path):
    p = tmp_path / "merchants.yaml"
    p.write_text(RULES, encoding="utf-8")
    return load_merchants(p)


def test_aliases_resolve_to_the_same_merchant(index):
    assert index.resolve("サンプルストア ワタダ") == "sample_store"
    assert index.resolve("サンプルストア 和多田店") == "sample_store"


def test_dictionary_bridges_katakana_and_kanji(index):
    """★これが本命。カード明細と領収書で表記が揃わない問題を辞書で解く。

    この2つの文字列そのものの類似度は低い。辞書が無いと突合できない。
    """
    card = "サンプルストア ワタダ"
    receipt = "サンプルストア 和多田店"
    assert similarity(card, receipt) < 1.0
    assert index.match_score(card, receipt) == 1.0


def test_different_merchants_score_zero_even_if_similar(index):
    """★辞書で別の店だと分かっているなら、文字列が似ていても一致させない。"""
    assert index.match_score("サンプルストア", "サンプル電機") == 0.0


def test_unknown_names_fall_back_to_similarity(index):
    score = index.match_score("未登録ストア", "未登録ストア北店")
    assert 0.6 <= score < 1.0


def test_one_side_unknown_falls_back(index):
    assert index.match_score("サンプルストア", "サンプルストア") == 1.0


def test_missing_file_gives_an_empty_index(tmp_path):
    idx = load_merchants(tmp_path / "absent.yaml")
    assert len(idx) == 0
    assert idx.resolve("サンプルストア") is None


def test_empty_index_still_compares_by_similarity():
    idx = MerchantIndex([])
    assert idx.match_score("サンプルストア", "サンプルストア") == 1.0


def test_canonical_name_is_available(index):
    assert index.canonical_name("sample_store") == "サンプルストア"


def test_merchant_dataclass_defaults():
    m = Merchant(id="x", canonical="X")
    assert m.aliases == ()
