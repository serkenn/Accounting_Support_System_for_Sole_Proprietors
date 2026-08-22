"""元帳（Beancount）まわり。

★ Beancount と beanquery は GPL-2.0-only。本パッケージは MIT なので
   `import` せず、外部コマンドとして呼ぶ（D57 / THIRD_PARTY_NOTICES.md）。
   この境界は tests/test_license_boundary.py が守っている。
"""

from .check import BeanCheckResult, bean_check, bean_check_available
from .query import bean_query_available, load_postings, run_query

__all__ = [
    "BeanCheckResult",
    "bean_check",
    "bean_check_available",
    "bean_query_available",
    "load_postings",
    "run_query",
]
