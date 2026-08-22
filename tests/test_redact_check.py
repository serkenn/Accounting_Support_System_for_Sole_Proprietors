"""機密文字列検査のテスト。

第1部 §11 S4 / 第13部 §6.1。
このテストは実装より先に書かれている。ここが緩むと他の全部が無意味になる。
"""

from __future__ import annotations

import json

import pytest

from conftest import (
    fake_bank_account,
    fake_card_number,
    fake_email,
    fake_my_number,
    fake_non_luhn_16,
    fake_phone,
)
from shiwake.safety import Denylist, Scanner

# ──────────────────────────────────────────────────────────
# 高信頼シグネチャ — 文脈なしでエラーにしてよいもの
# ──────────────────────────────────────────────────────────


def test_luhn_card_number_is_error():
    findings = Scanner().scan_text(f"カード {fake_card_number()} で決済")
    assert [f.rule for f in findings] == ["card_number"]
    assert findings[0].severity == "error"


def test_sixteen_digits_failing_luhn_is_not_a_card():
    findings = Scanner().scan_text(f"注文番号 {fake_non_luhn_16()}")
    assert not any(f.rule == "card_number" for f in findings)


def test_card_number_with_separators_is_detected():
    c = fake_card_number()
    spaced = f"{c[0:4]} {c[4:8]} {c[8:12]} {c[12:16]}"
    hyphened = spaced.replace(" ", "-")
    assert any(f.rule == "card_number" for f in Scanner().scan_text(spaced))
    assert any(f.rule == "card_number" for f in Scanner().scan_text(hyphened))


def test_email_is_error():
    findings = Scanner().scan_text(f"連絡先は {fake_email()} です")
    assert any(f.rule == "email" and f.severity == "error" for f in findings)


def test_reserved_example_domains_are_allowed():
    """ドキュメントで使う予約ドメインは誤検知にしない（第13部 §7.1）。"""
    text = "問い合わせ: user@example.com / admin@example.invalid / a@foo.test"
    assert not any(f.rule == "email" for f in Scanner().scan_text(text))


def test_phone_number_is_error():
    findings = Scanner().scan_text(f"電話 {fake_phone()}")
    assert any(f.rule == "phone" and f.severity == "error" for f in findings)


def test_private_key_header_is_error():
    text = "-----BEGIN" + " RSA PRIVATE KEY-----"
    assert any(f.rule == "private_key" for f in Scanner().scan_text(text))


# ──────────────────────────────────────────────────────────
# 文脈つきシグネチャ — キー名と併せて判定するもの
# ──────────────────────────────────────────────────────────


def test_my_number_with_context_is_error():
    findings = Scanner().scan_text(f'"個人番号": "{fake_my_number()}"')
    assert any(f.rule == "my_number" and f.severity == "error" for f in findings)


def test_my_number_english_key_is_error():
    findings = Scanner().scan_text(f'my_number = "{fake_my_number()}"')
    assert any(f.rule == "my_number" for f in findings)


def test_pension_number_with_context_is_error():
    text = "基礎年金番号 1234-567890"  # redact-check: ignore
    assert any(f.rule == "pension_number" for f in Scanner().scan_text(text))


def test_bank_account_key_with_full_number_is_error():
    doc = json.dumps({"account_no": fake_bank_account()}, ensure_ascii=False)
    findings = Scanner().scan_text(doc, path="doc.json")
    assert any(f.rule == "bank_account" and f.severity == "error" for f in findings)


def test_bank_account_last4_only_is_clean():
    """下4桁だけの保持は仕様上ゆるされている（第1部 §5）。"""
    doc = json.dumps({"account_no_last4": "1234", "card_last4": "5678"}, ensure_ascii=False)
    assert Scanner().scan_text(doc, path="doc.json") == []


# ──────────────────────────────────────────────────────────
# 裸の数字列 — 誤検知を避けるため既定は warning
# ──────────────────────────────────────────────────────────


def test_bare_twelve_digit_string_is_warning_not_error():
    doc = json.dumps({"memo": fake_my_number()}, ensure_ascii=False)
    findings = Scanner().scan_text(doc, path="doc.json")
    assert [f.severity for f in findings] == ["warning"]
    assert findings[0].rule == "bare_digits_12"


def test_bare_digits_become_error_under_strict():
    doc = json.dumps({"memo": fake_my_number()}, ensure_ascii=False)
    findings = Scanner(strict=True).scan_text(doc, path="doc.json")
    assert any(f.rule == "bare_digits_12" and f.severity == "error" for f in findings)


def test_amount_as_json_number_is_never_flagged():
    """★金額は数値として書かれる。7桁・12桁の金額で検査が鳴ったら誰も使わなくなる。"""
    doc = json.dumps(
        {"total": 1234567, "statement_total": 123456789012, "balance": 9999999},
        ensure_ascii=False,
    )
    assert Scanner(strict=True).scan_text(doc, path="doc.json") == []


def test_sha256_hex_is_not_flagged():
    doc = json.dumps({"original_ref": "sha256:" + "a1b2c3d4" * 8}, ensure_ascii=False)
    assert Scanner(strict=True).scan_text(doc, path="doc.json") == []


def test_iso_dates_and_ids_are_not_flagged():
    doc = json.dumps(
        {"issued_at": "2026-08-14T19:23:00+09:00", "doc_id": "doc_2026-08-14_store_a1b2c3"},
        ensure_ascii=False,
    )
    assert Scanner(strict=True).scan_text(doc, path="doc.json") == []


# ──────────────────────────────────────────────────────────
# 名前ベースの層（第13部 §6.1 第1層）
# ──────────────────────────────────────────────────────────


def test_denylist_term_in_content_is_error():
    dl = Denylist(["架空商事"])
    findings = Scanner(denylist=dl).scan_text("架空商事 御中")
    assert any(f.rule == "denylist" and f.severity == "error" for f in findings)


def test_denylist_is_case_insensitive():
    dl = Denylist(["AcmeCorp"])
    assert any(f.rule == "denylist" for f in Scanner(denylist=dl).scan_text("acmecorp inc"))


def test_denylist_matches_file_path(tmp_path):
    dl = Denylist(["架空商事"])
    p = tmp_path / "架空商事_invoice.json"
    p.write_text("{}", encoding="utf-8")
    findings = Scanner(denylist=dl).scan_file(p)
    assert any(f.rule == "denylist_path" for f in findings)


def test_denylist_applies_to_commit_message():
    """第13部 §6.3 — コミットメッセージからも漏れる。"""
    dl = Denylist(["架空商事"])
    findings = Scanner(denylist=dl).scan_commit_message("fix: 架空商事の請求書パースを修正")
    assert any(f.rule == "denylist" for f in findings)


def test_empty_denylist_never_matches():
    assert Scanner(denylist=Denylist([])).scan_text("なんでもない文章") == []


# ──────────────────────────────────────────────────────────
# 検出結果そのものが漏洩経路にならないこと
# ──────────────────────────────────────────────────────────


def test_excerpt_never_contains_the_full_secret():
    """★検出器がログに秘密を書き出したら本末転倒（第7部 §1 と同じ考え方）。"""
    card = fake_card_number()
    findings = Scanner().scan_text(f"カード {card}")
    assert findings
    for f in findings:
        assert card not in f.excerpt
        assert card not in f.message
        assert card not in str(f)


def test_denylist_finding_does_not_echo_the_term():
    dl = Denylist(["架空商事"])
    findings = Scanner(denylist=dl).scan_text("架空商事 御中")
    assert findings
    for f in findings:
        assert "架空商事" not in f.excerpt
        assert "架空商事" not in f.message


# ──────────────────────────────────────────────────────────
# 抑制
# ──────────────────────────────────────────────────────────


def test_inline_ignore_comment_suppresses_that_line():
    text = f"sample = '{fake_card_number()}'  # redact-check: ignore"
    assert Scanner().scan_text(text) == []


def test_inline_ignore_does_not_leak_to_other_lines():
    text = f"a = 1  # redact-check: ignore\nb = '{fake_card_number()}'"
    findings = Scanner().scan_text(text)
    assert any(f.rule == "card_number" for f in findings)
    assert findings[0].line == 2


# ──────────────────────────────────────────────────────────
# ファイル走査
# ──────────────────────────────────────────────────────────


def test_binary_files_are_skipped(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    assert Scanner().scan_file(p) == []


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        Scanner().scan_file(tmp_path / "nope.txt")


def test_line_numbers_are_one_based():
    text = "ok\nok\n" + fake_email()
    findings = Scanner().scan_text(text)
    assert findings[0].line == 3


# ──────────────────────────────────────────────────────────
# 郵便番号 + 住所（第13部 §6.2）
# ──────────────────────────────────────────────────────────


def test_postal_code_with_address_context_is_error():
    text = "〒123-4567 ○○県△△市□□町1丁目2番3号"  # redact-check: ignore
    assert any(f.rule == "postal_address" for f in Scanner().scan_text(text))


def test_postal_code_without_address_context_is_clean():
    """住所を示す語が無い 3-4 桁の組は、伝票番号などでも普通に出る。"""
    text = "整理番号 123-4567"
    assert not any(f.rule == "postal_address" for f in Scanner().scan_text(text))


def test_address_finding_is_masked():
    text = "〒123-4567 ○○県△△市□□町1丁目"  # redact-check: ignore
    findings = [f for f in Scanner().scan_text(text) if f.rule == "postal_address"]
    assert findings and "123-4567" not in findings[0].excerpt


# ──────────────────────────────────────────────────────────
# 除外パス（事務処理規程などは実名が入っているのが正しい）
# ──────────────────────────────────────────────────────────


def test_excluded_directory_is_skipped(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    p = docs / "事務処理規程.md"
    p.write_text(f"連絡先 {fake_email()}", encoding="utf-8")
    assert Scanner(exclude=["docs/"]).scan_file(p) == []


def test_non_excluded_directory_is_still_scanned(tmp_path):
    other = tmp_path / "documents"
    other.mkdir()
    p = other / "doc.json"
    p.write_text(f'{{"notes": "{fake_email()}"}}', encoding="utf-8")
    assert any(f.rule == "email" for f in Scanner(exclude=["docs/"]).scan_file(p))


# ──────────────────────────────────────────────────────────
# 誤検知の抑制 — ここが緩むと検査が無視されるようになる
# ──────────────────────────────────────────────────────────


def test_bare_integer_literal_in_python_is_not_flagged():
    """金額の定数は普通に7桁になる。ここで鳴る検査は使われなくなる。"""
    text = "TOTAL = 1234567\n"  # redact-check: ignore
    assert Scanner(strict=True).scan_text(text, path="x.py") == []


def test_bare_integer_in_beancount_is_not_flagged():
    text = "  Expenses:Business:Supplies    1234567 JPY\n"  # redact-check: ignore
    assert Scanner(strict=True).scan_text(text, path="ledger/generated/2026-08.beancount") == []


def test_amount_column_in_csv_is_not_flagged():
    text = "2026-08-14,サンプルストア,1234567\n"  # redact-check: ignore
    assert Scanner(strict=True).scan_text(text, path="exports/仕訳帳.csv") == []


def test_quoted_digits_in_python_are_still_flagged():
    """文字列として書かれた番号は数値ではない。こちらは見逃さない。"""
    text = 'ACCOUNT = "1234567"\n'  # redact-check: ignore
    findings = Scanner(strict=True).scan_text(text, path="x.py")
    assert any(f.rule == "bare_digits_7" for f in findings)


def test_prose_files_still_flag_bare_digits():
    """散文には型が無いので、取りこぼさない側に倒す。"""
    text = "番号は 991111111111 です\n"  # redact-check: ignore
    findings = Scanner(strict=True).scan_text(text, path="notes.md")
    assert any(f.rule == "bare_digits_12" for f in findings)


def test_lockfile_sizes_are_not_flagged():
    """ロックファイルにはパッケージのサイズが7桁で並ぶ。ここで鳴ると常に赤くなる。"""
    text = (
        'sdist = { url = "https://example.com/a.tar.gz", size = 5005329 }\n'  # redact-check: ignore
    )
    assert Scanner(strict=True).scan_text(text, path="uv.lock") == []
