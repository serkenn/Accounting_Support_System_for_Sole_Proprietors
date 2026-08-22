"""元帳（Beancount）まわり。

★ Beancount と beanquery は GPL-2.0-only。本パッケージは MIT なので
   `import` せず、外部コマンドとして呼ぶ（D57 / THIRD_PARTY_NOTICES.md）。
   この境界は tests/test_license_boundary.py が守っている。
"""

from .build import BuildResult, build_month, card_debit_transaction
from .categorize import Categorizer, load_categories
from .check import BeanCheckResult, bean_check, bean_check_available
from .merchants import MerchantIndex, load_merchants
from .query import bean_query_available, load_postings, run_query
from .reconcile import CardLine, Links, Receipt, find_candidates, load_links, save_links

__all__ = [
    "BeanCheckResult",
    "BuildResult",
    "CardLine",
    "Categorizer",
    "Links",
    "MerchantIndex",
    "Receipt",
    "bean_check",
    "bean_check_available",
    "bean_query_available",
    "build_month",
    "card_debit_transaction",
    "find_candidates",
    "load_categories",
    "load_links",
    "load_merchants",
    "load_postings",
    "run_query",
    "save_links",
]
