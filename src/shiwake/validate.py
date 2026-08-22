"""document の検証（第1部 §9 の `make check` / §6 の検算）。

2層に分ける。

  1. JSON Schema   構造。書いてよい形かどうか
  2. 業務ルール     数字が合うかどうか

★2 が本体。「合計が内訳と一致しないとき、内訳を改変して合わせない」
（第1部 §9.1）を守らせるには、合わないことを検出して
needs_review へ隔離させるしかない。黙って通すと、あとで気づけない。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).parent / "schemas"

Severity = Literal["error", "warning"]

#: 型ごとのスキーマファイル
SCHEMA_FILES = {
    "receipt": "receipt.schema.json",
    "card_statement": "card_statement.schema.json",
    "payslip": "payslip.schema.json",
}


@dataclass(frozen=True, order=True)
class Issue:
    path: str
    severity: Severity
    rule: str
    message: str

    def format(self) -> str:
        mark = "ERROR  " if self.severity == "error" else "WARNING"
        return f"{mark} {self.path}  [{self.rule}] {self.message}"


@cache
def _registry() -> Registry:
    registry = Registry()
    for file in SCHEMA_DIR.glob("*.schema.json"):
        contents = json.loads(file.read_text(encoding="utf-8"))
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = resource @ registry
        # 相対参照（"common.schema.json#/$defs/..."）でも引けるようにする
        registry = registry.with_resource(file.name, resource)
    return registry


@cache
def schema_for(doc_type: str) -> dict[str, Any] | None:
    name = SCHEMA_FILES.get(doc_type)
    if name is None:
        return None
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _validator(doc_type: str) -> Draft202012Validator | None:
    schema = schema_for(doc_type)
    if schema is None:
        return None
    return Draft202012Validator(schema, registry=_registry())


# ── 業務ルール ──────────────────────────────────────────


def _total(values: Iterable[Any]) -> int | None:
    """None が混ざったら合計しない。推測で 0 として扱わない。"""
    out = 0
    for v in values:
        if not isinstance(v, int):
            return None
        out += v
    return out


def _flagged(doc: dict) -> bool:
    return bool(doc.get("needs_review")) and bool(doc.get("review_reason"))


def _check_business_rules(doc: dict, path: str) -> list[Issue]:
    issues: list[Issue] = []

    def err(rule: str, message: str) -> None:
        issues.append(Issue(path, "error", rule, message))

    def warn(rule: str, message: str) -> None:
        issues.append(Issue(path, "warning", rule, message))

    def err_unless_flagged(rule: str, message: str) -> None:
        """数字が合わないが、人が needs_review で隔離済みなら通す。

        「内訳を改変して合わせない」（第1部 §9.1）を守るための逃げ道。
        隔離せずに合わないまま進むことだけを止める。
        """
        if not _flagged(doc):
            err(rule, message)

    doc_type = doc.get("type")

    # ── 推測で埋めない（第1部 §9.1 の3・4）──────────────
    if doc.get("needs_review") and not doc.get("review_reason"):
        err("missing_review_reason", "needs_review を立てたら理由を書いてください")

    if _has_null_amount(doc) and not _flagged(doc):
        err(
            "null_without_review",
            "読み取れなかった金額があります。needs_review と review_reason を立ててください",
        )

    # ── 紙と電子の区分（第9部 §9）──────────────────────
    if doc.get("origin") == "paper":
        retained = doc.get("paper_retained")
        scanner = doc.get("scanner_storage")
        if retained is False and not scanner:
            warn(
                "paper_not_retained",
                "紙を保管しておらず、スキャナ保存の要件も満たしていません。"
                "この証憑は失われた扱いになります",
            )

    # ── 第1部 §6 の検算 ────────────────────────────────
    if doc_type == "card_statement":
        declared = doc.get("statement_total")
        summed = _total(t.get("amount") for t in doc.get("transactions", []))
        if declared is not None and summed is not None and declared != summed:
            # ★ここは needs_review で免除しない。明細の取りこぼしは
            #   人が見ても直らず、取り込み直しが必要になるため。
            err(
                "statement_total_mismatch",
                f"明細の合計 {summed:,} が請求総額 {declared:,} と一致しません"
                f"（差 {declared - summed:+,}）。取り込み漏れの可能性があります",
            )

    if doc_type == "receipt":
        total = doc.get("total")
        lines_sum = _total(line.get("amount") for line in doc.get("lines", []))
        if total is not None and lines_sum is not None and lines_sum and total != lines_sum:
            err_unless_flagged(
                "total_mismatch",
                f"内訳の合計 {lines_sum:,} が合計額 {total:,} と一致しません。"
                "内訳を書き換えて合わせず、needs_review にしてください",
            )

        breakdown = doc.get("tax_breakdown") or []
        tax_sum = _total(
            v for entry in breakdown for v in (entry.get("taxable_amount"), entry.get("tax_amount"))
        )
        if total is not None and tax_sum is not None and breakdown and total != tax_sum:
            err_unless_flagged(
                "tax_breakdown_mismatch",
                f"税率別内訳の合計 {tax_sum:,} が合計額 {total:,} と一致しません"
                "（税込経理のため一致するはずです）",
            )

    # ── 第5部 §11 の検算 ───────────────────────────────
    if doc_type == "payslip":
        gross = doc.get("gross")
        net = doc.get("net")
        earn_sum = _total(e.get("amount") for e in doc.get("earnings", []))
        ded_sum = _total(d.get("amount") for d in doc.get("deductions", []))

        if gross is not None and earn_sum is not None and gross != earn_sum:
            err_unless_flagged(
                "payslip_gross_mismatch",
                f"支給の合計 {earn_sum:,} が総支給額 {gross:,} と一致しません",
            )
        if None not in (gross, net) and ded_sum is not None and gross - ded_sum != net:
            err_unless_flagged(
                "payslip_net_mismatch",
                f"総支給 {gross:,} − 控除 {ded_sum:,} = {gross - ded_sum:,} が"
                f"手取り {net:,} と一致しません",
            )

    return issues


def _has_null_amount(node: Any) -> bool:
    """金額を表すキーに null が入っているか。"""
    money_keys = {
        "total",
        "amount",
        "unit_price",
        "statement_total",
        "gross",
        "net",
        "taxable_amount",
        "tax_amount",
        "commute_allowance",
    }
    if isinstance(node, dict):
        return any(
            (key in money_keys and value is None) or _has_null_amount(value)
            for key, value in node.items()
        )
    if isinstance(node, list):
        return any(_has_null_amount(item) for item in node)
    return False


# ── 入口 ────────────────────────────────────────────────


def validate_document(doc: dict, path: str = "<document>") -> list[Issue]:
    doc_type = doc.get("type")
    validator = _validator(doc_type) if isinstance(doc_type, str) else None
    if validator is None:
        return [Issue(path, "error", "unknown_type", f"未知の document 型です: {doc_type!r}")]

    issues = [
        Issue(
            path,
            "error",
            "schema",
            f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}",
        )
        for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    ]
    if issues:
        # 構造が壊れているうちは業務ルールの検算に意味がない
        return issues
    return _check_business_rules(doc, path)


def validate_file(path: Path) -> list[Issue]:
    rel = str(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [Issue(rel, "error", "invalid_json", f"JSON として読めません: 行 {e.lineno}")]
    except UnicodeDecodeError:
        return [Issue(rel, "error", "invalid_json", "UTF-8 として読めません")]

    if not isinstance(doc, dict):
        return [Issue(rel, "error", "invalid_json", "オブジェクトではありません")]

    issues = validate_document(doc, rel)
    if doc.get("doc_id") and doc["doc_id"] != path.stem:
        issues.append(
            Issue(
                rel,
                "error",
                "doc_id_filename_mismatch",
                f"doc_id とファイル名が一致しません（ファイル名: {path.stem}）",
            )
        )
    return issues


def validate_paths(paths: Iterable[Path]) -> list[Issue]:
    issues: list[Issue] = []
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*.json")):
                issues.extend(validate_file(child))
        elif path.is_file():
            issues.extend(validate_file(path))
    return sorted(issues)
