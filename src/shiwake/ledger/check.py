"""`bean-check` の呼び出し。

Beancount のデータ構造には触れない。ファイルを渡して、
終了コードと出力だけを受け取る。
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

BEAN_CHECK = "bean-check"


class BeanCheckMissingError(RuntimeError):
    """`bean-check` が見つからない。"""


@dataclass(frozen=True)
class BeanCheckResult:
    ok: bool
    output: str

    @property
    def lines(self) -> list[str]:
        return [line for line in self.output.splitlines() if line.strip()]


def bean_check_available() -> bool:
    return shutil.which(BEAN_CHECK) is not None


def bean_check(main_file: Path, timeout: int = 120) -> BeanCheckResult:
    """元帳を検査する。

    見つからない場合は黙って成功にしない。検査していないのに
    通ったように見えるのが一番まずい。
    """
    if not bean_check_available():
        raise BeanCheckMissingError(
            f"{BEAN_CHECK} が見つかりません。`uv tool install beancount` で入れてください。"
        )
    if not main_file.is_file():
        raise FileNotFoundError(main_file)

    proc = subprocess.run(
        [BEAN_CHECK, str(main_file)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (proc.stdout + proc.stderr).strip()
    return BeanCheckResult(ok=proc.returncode == 0, output=output)
