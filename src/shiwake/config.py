"""設定とパスの解決。

第9部 §3.1 は `/srv/ledger` `/srv/inbox` `/srv/files` を前提に書かれているが、
同じデータリポジトリが開発機（macOS）と本番（LXC）の両方に置かれる。
そこでパスを設定値にし、マシンごとに上書きできるようにする。

  .shiwake.toml        コミットする。本番の値
  .shiwake.local.toml  .gitignore。そのマシンだけの上書き
  環境変数              CI や一時的な差し替え用（最優先）

第13部 §11「固有の値を全部外出しする」に沿った作りでもある。
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = "config.toml"
MAIN_CONFIG = ".shiwake.toml"
LOCAL_CONFIG = ".shiwake.local.toml"

ENV_PREFIX = "SHIWAKE_"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Paths:
    """データリポジトリから見た各ディレクトリ。"""

    root: Path
    inbox: Path
    files: Path

    @property
    def originals(self) -> Path:
        """原本。ここへは scripts 経由でしか書かない（第9部 §3.5 / S14）。"""
        return self.files / "originals"

    @property
    def derived(self) -> Path:
        """表示用派生。再生成できるのでバックアップ対象外（第8部 §2.2）。"""
        return self.files / "derived"

    @property
    def failed(self) -> Path:
        """取り込みに失敗したもの。黙って消さない（第9部 §7）。"""
        return self.inbox / "failed"

    @property
    def inbox_paper(self) -> Path:
        """紙を撮影・スキャンしたもの → origin: paper。"""
        return self.inbox / "paper"

    @property
    def inbox_electronic(self) -> Path:
        """電子で受け取ったファイル → origin: electronic。"""
        return self.inbox / "electronic"


@dataclass(frozen=True)
class SafetyConfig:
    """漏洩検査の設定。"""

    #: 検査から外すパス。実名が入っているのが正しい文書のみを明示的に挙げる
    exclude: tuple[str, ...] = ()
    #: 固有名詞の一覧（第13部 §6.1 第1層）
    denylist: Path | None = None
    strict: bool = False


@dataclass(frozen=True)
class Config:
    paths: Paths
    safety: SafetyConfig = field(default_factory=SafetyConfig)


def find_root(start: Path | None = None) -> Path:
    """`.shiwake.toml` を上に向かって探す。"""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / MAIN_CONFIG).is_file():
            return candidate
    raise ConfigError(f"{MAIN_CONFIG} が見つかりません。データリポジトリの中で実行してください。")


def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path)


def load(root: Path | None = None) -> Config:
    """設定を読み込む。`.shiwake.toml` → `.shiwake.local.toml` → 環境変数 の順に上書き。"""
    root = root or find_root()
    data = _merge(_read(root / MAIN_CONFIG), _read(root / LOCAL_CONFIG))

    raw_paths = dict(data.get("paths", {}))
    for key in ("inbox", "files"):
        env = os.environ.get(f"{ENV_PREFIX}{key.upper()}")
        if env:
            raw_paths[key] = env

    missing = [k for k in ("inbox", "files") if not raw_paths.get(k)]
    if missing:
        raise ConfigError(f"{MAIN_CONFIG} の [paths] に {', '.join(missing)} がありません。")

    paths = Paths(
        root=root,
        inbox=_resolve(root, raw_paths["inbox"]),
        files=_resolve(root, raw_paths["files"]),
    )

    raw_safety = data.get("safety", {})
    denylist = raw_safety.get("denylist")
    safety = SafetyConfig(
        exclude=tuple(raw_safety.get("exclude", ())),
        denylist=_resolve(root, denylist) if denylist else None,
        strict=bool(raw_safety.get("strict", False)),
    )

    return Config(paths=paths, safety=safety)
