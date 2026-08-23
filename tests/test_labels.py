"""画面に出す科目の名前（第3部 §4）。"""

from __future__ import annotations

import textwrap

from shiwake.web.labels import DEFAULT_LABELS, label_for, load_labels, missing_labels


def test_business_account_uses_the_tax_form_wording():
    """★決算書と同じ言葉にする。画面と申告書で別の名前になると説明できない。"""
    assert label_for("Expenses:Business:Supplies") == "消耗品費"
    assert label_for("Expenses:Business:Travel") == "旅費交通費"


def test_leaf_falls_back_to_the_category_level():
    """集計は Expenses:<名前空間>:<費目> の粒度。葉まで名前を持たない。"""
    assert label_for("Expenses:Personal:Food:Groceries") == "食費"
    assert label_for("Expenses:Business:Utilities:Electricity") == "水道光熱費"


def test_unknown_account_returns_none_not_english():
    """★英語のまま出すくらいなら、無いことを知らせる。

    黙って英語が出ると、抜けていることに誰も気づかない。
    実際に画面に「Supplies」「Food」と出ていた。
    """
    assert label_for("Expenses:Business:Mystery") is None


def test_missing_labels_are_reported():
    accounts = ["Expenses:Business:Supplies", "Expenses:Business:Mystery"]
    assert missing_labels(accounts) == ["Expenses:Business:Mystery"]


def test_data_repo_can_override(tmp_path):
    p = tmp_path / "labels.yaml"
    p.write_text(
        textwrap.dedent(
            """
            labels:
              "Expenses:Personal:Food": 食料品
              "Expenses:Personal:Hobby": 趣味
            """
        ),
        encoding="utf-8",
    )
    labels = load_labels(p)
    assert label_for("Expenses:Personal:Food", labels) == "食料品"
    assert label_for("Expenses:Personal:Hobby", labels) == "趣味"
    # 上書きしていないものは既定のまま
    assert label_for("Expenses:Business:Supplies", labels) == "消耗品費"


def test_missing_file_gives_the_defaults(tmp_path):
    assert load_labels(tmp_path / "nope.yaml") == DEFAULT_LABELS


def test_no_label_is_left_in_english():
    """★既定の表に英語が紛れていないこと。"""
    for account, label in DEFAULT_LABELS.items():
        assert not label.isascii(), f"{account} の表示名が英語のままです: {label}"
