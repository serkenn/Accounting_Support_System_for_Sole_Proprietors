"""機密情報の漏洩を機械的に止める層。

第1部 §11 S4（コミット前の機械的検査）と
第13部 §6.1（検査を2層に分ける）の実装。
"""

from .denylist import Denylist
from .findings import Finding, Severity, mask, mask_fully
from .scanner import Scanner

__all__ = ["Denylist", "Finding", "Scanner", "Severity", "mask", "mask_fully"]
