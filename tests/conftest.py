"""テスト用のヘルパ。

★ここで扱う「機密に見える文字列」は、すべて実行時に組み立てる。
   ソースコードに直接書くと、公開リポジトリ自身の漏洩検査
   （scripts/check_public_safe.py）に引っかかってしまうため。
   すべて架空の値であり、実在の口座・カード・個人とは無関係。
"""

from __future__ import annotations


def luhn_check_digit(prefix: str) -> str:
    """先頭の数字列に対する Luhn のチェックディジットを返す。"""
    total = 0
    for i, ch in enumerate(reversed(prefix)):
        d = int(ch)
        if i % 2 == 0:  # チェックディジットを足した後に偶数位置となる桁
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def fake_card_number() -> str:
    """Luhn を通る 16 桁の架空のカード番号を組み立てる。"""
    prefix = "4" + "2" * 14  # 15桁
    return prefix + luhn_check_digit(prefix)


def fake_non_luhn_16() -> str:
    """16 桁だが Luhn を通らない数字列。"""
    card = fake_card_number()
    wrong = str((int(card[-1]) + 1) % 10)
    return card[:-1] + wrong


def fake_my_number() -> str:
    """架空のマイナンバー（12桁）。"""
    return "9" * 6 + "1" * 6


def fake_bank_account() -> str:
    """架空の口座番号（7桁）。"""
    return "8" * 7


def fake_email() -> str:
    """検査に引っかかるべき架空のメールアドレス（予約ドメインは使わない）。"""
    return "a" + "bc" + "@" + "kaikei-" + "sample" + ".jp"


def fake_phone() -> str:
    """架空の固定電話番号。"""
    return "0" + "955" + "-" + "12" + "-" + "3456"
