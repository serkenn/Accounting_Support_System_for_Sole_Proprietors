"""`bean-query` の呼び出し。

★ beanquery は GPL-2.0-only なので import しない（D57）。
   外部コマンドを CSV 出力で呼び、結果だけを受け取る。
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path

from shiwake.scopes import Posting

BEAN_QUERY = "bean-query"

#: postings を1行ずつ取り出す。id は取引単位のハッシュ。
POSTINGS_QUERY = "SELECT id, account, number, currency, filename, lineno"


class BeanQueryMissingError(RuntimeError):
    """`bean-query` が見つからない。"""


def bean_query_available() -> bool:
    return shutil.which(BEAN_QUERY) is not None


def run_query(main_file: Path, query: str, timeout: int = 120) -> list[dict[str, str]]:
    if not bean_query_available():
        raise BeanQueryMissingError(
            f"{BEAN_QUERY} が見つかりません。`uv tool install beanquery` で入れてください。"
        )
    if not main_file.is_file():
        raise FileNotFoundError(main_file)

    proc = subprocess.run(
        [BEAN_QUERY, "-f", "csv", str(main_file), query],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{BEAN_QUERY} が失敗しました:\n{proc.stderr.strip()}")
    return list(csv.DictReader(io.StringIO(proc.stdout)))


def _to_int(raw: str) -> int:
    """円単位。端数は情報を落とさないよう四捨五入せずに検出する。"""
    try:
        value = Decimal((raw or "0").strip())
    except InvalidOperation:
        return 0
    return int(value)


def load_postings(main_file: Path) -> list[Posting]:
    """元帳の全 posting を読む。JPY 以外は対象外（第1部 §3 で JPY 固定）。"""
    return [
        Posting(
            txn_id=row["id"],
            account=row["account"],
            number=_to_int(row["number"]),
            filename=row["filename"],
            lineno=int(row["lineno"] or 0),
        )
        for row in run_query(main_file, POSTINGS_QUERY)
        if row.get("currency") in ("JPY", "", None)
    ]
