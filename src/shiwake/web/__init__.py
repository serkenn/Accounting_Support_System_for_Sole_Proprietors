"""Web に渡す静的データの生成（第1部 §10 / 第3部）。

Web はバックエンドを持たない。元帳から作った静的 JSON を
ブラウザが読んで描く（第1部 §8、第9部 §10 で「読みは静的」に確定）。

★ここで作る JSON が、画面に出る数字の唯一の出どころになる。
  画面側で計算し直さない。二重に実装すると必ずズレるし、
  ズレたときにどちらが正しいか分からなくなる。
"""

from .build_data import LedgerPosting, WebData, build_web_data

__all__ = ["LedgerPosting", "WebData", "build_web_data"]
