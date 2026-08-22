"""依存のピンを検査する（第13部 §4・§12）。

★公開側の変更で、自分の帳簿の計算が黙って変わるのを防ぐ。

  main に追従させると、`uv sync` するたびに計算が変わりうる。
  申告済みの年度の数字が変わったら重大事案なので、
  上げるときは意図的に上げ、上げた後に全期間を再計算して差分を確認する。

人が忘れると静かに壊れる種類のものなので、機械で止める。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

#: 追従してしまう指定。バージョンが動く
FLOATING = re.compile(
    r"@(main|master|HEAD|develop)\b"  # ブランチ追従
    r"|(?<![=~^])>=\s*\d"  # 下限だけの指定
    r"|\*\s*$",  # ワイルドカード
    re.IGNORECASE,
)

#: 固定されている指定
PINNED = re.compile(r"@v?\d+\.\d+|==\s*\d+\.\d+|@[0-9a-f]{40}\b")


@dataclass(frozen=True)
class PinProblem:
    dependency: str
    message: str

    def format(self) -> str:
        return f"ERROR   [pin] {self.dependency}: {self.message}"


def check_pins(pyproject: Path, names: tuple[str, ...] = ("shiwake",)) -> list[PinProblem]:
    """指定した依存が固定されているかを見る。"""
    if not pyproject.is_file():
        return [PinProblem(str(pyproject), "pyproject.toml がありません")]

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = list(data.get("project", {}).get("dependencies", []))
    problems: list[PinProblem] = []

    for name in names:
        matching = [d for d in deps if d.split()[0].split("[")[0].split("=")[0].strip() == name]
        if not matching:
            problems.append(PinProblem(name, "依存として宣言されていません"))
            continue
        for spec in matching:
            if FLOATING.search(spec):
                problems.append(
                    PinProblem(
                        name,
                        "バージョンが固定されていません。"
                        "追従させると、公開側の変更で帳簿の計算が黙って変わります（第13部 §4）",
                    )
                )
            elif not PINNED.search(spec):
                problems.append(
                    PinProblem(name, "タグまたはバージョンで固定してください（第13部 §4）")
                )

    # ★ローカルパス参照は開発中の便宜であって、運用では使えない
    sources = data.get("tool", {}).get("uv", {}).get("sources", {})
    for name in names:
        source = sources.get(name)
        if isinstance(source, dict) and ("path" in source or source.get("editable")):
            problems.append(
                PinProblem(
                    name,
                    "ローカルのパスを参照しています。"
                    "手元では動きますが、他のマシンでは解決できません",
                )
            )

    return problems
