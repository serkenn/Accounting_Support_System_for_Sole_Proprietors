"""明細のパース。

★カード明細のパースは、必ず**請求総額との検算**を伴う。
  合わないのは抽出漏れであり、そのまま進めると
  二重計上の防止（第1部 §6）の前提が崩れる。
"""

from .statement import StatementLine, StatementParseResult, parse_card_statement_text

__all__ = ["StatementLine", "StatementParseResult", "parse_card_statement_text"]
