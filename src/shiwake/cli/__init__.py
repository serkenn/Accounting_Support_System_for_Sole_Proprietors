"""shiwake のコマンドライン入口。

Phase 0.5 の時点では安全性の検査だけを提供する。
取り込み・元帳生成などは各フェーズで追加する。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from shiwake import validate as vd
from shiwake.ledger import bean_check
from shiwake.ledger.check import BeanCheckMissingError
from shiwake.safety import Denylist, Scanner
from shiwake.safety import public_safe as ps


def _add_denylist_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--denylist",
        type=Path,
        default=None,
        help="固有名詞の一覧ファイル。未指定なら既定の置き場を探す",
    )


def cmd_redact_check(args: argparse.Namespace) -> int:
    denylist = Denylist.discover(args.denylist)
    scanner = Scanner(denylist=denylist, strict=args.strict, exclude=args.exclude)

    if args.message_file:
        text = Path(args.message_file).read_text(encoding="utf-8")
        findings = scanner.scan_commit_message(text)
    else:
        paths = [Path(p) for p in args.paths] or [Path(".")]
        findings = scanner.scan_paths(paths)

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    for f in findings:
        print(f.format(), file=sys.stderr)

    if not denylist:
        print(
            "NOTE    固有名詞リストが見つかりません。名前ベースの検査（第1層）は動いていません。\n"
            "        config/denylist.txt か ~/.config/shiwake/denylist.txt を用意してください。",
            file=sys.stderr,
        )

    print(f"\nredact-check: error {len(errors)} 件 / warning {len(warnings)} 件", file=sys.stderr)
    if errors:
        print("コミットを中止します。値を取り除いてからやり直してください。", file=sys.stderr)
        return 1
    return 0


def cmd_check_public_safe(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    denylist = Denylist.discover(args.denylist)
    exclude = tuple(args.exclude)

    problems = (
        ps.check_forbidden_files(root)
        + ps.check_fixtures_are_synthetic(root)
        + ps.check_tax_templates_are_null(root)
    )
    findings = ps.check_patterns(root, denylist, exclude) + ps.check_commit_messages(root, denylist)
    gitleaks_ok, gitleaks_msg = ps.run_gitleaks(root)

    for p in problems:
        print(p.format(), file=sys.stderr)
    for f in findings:
        print(f.format(), file=sys.stderr)
    print(gitleaks_msg, file=sys.stderr)

    errors = [f for f in findings if f.severity == "error"]
    failed = bool(problems) or bool(errors) or not gitleaks_ok

    print(
        f"\ncheck-public-safe: 構造の問題 {len(problems)} 件 / パターン error {len(errors)} 件",
        file=sys.stderr,
    )
    if failed:
        print("公開リポジトリに出せない状態です。", file=sys.stderr)
        return 1
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    paths = [Path(p) for p in args.paths] or [Path("documents")]
    missing = [p for p in paths if not p.exists()]
    for p in missing:
        print(f"NOTE    {p} がありません（まだ取り込んでいない状態です）", file=sys.stderr)
    issues = vd.validate_paths([p for p in paths if p.exists()])

    for i in issues:
        print(i.format(), file=sys.stderr)

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    print(f"\nvalidate: error {len(errors)} 件 / warning {len(warnings)} 件", file=sys.stderr)
    return 1 if errors else 0


def cmd_bean_check(args: argparse.Namespace) -> int:
    try:
        result = bean_check(Path(args.main))
    except BeanCheckMissingError as e:
        print(f"ERROR   {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"ERROR   元帳が見つかりません: {e}", file=sys.stderr)
        return 1

    for line in result.lines:
        print(line, file=sys.stderr)
    print(f"\nbean-check: {'OK' if result.ok else '不整合あり'}", file=sys.stderr)
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shiwake", description="証憑から仕訳を組み立てるツールキット"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("redact-check", help="機密文字列の検査（第1部 §11 S4）")
    p.add_argument("paths", nargs="*", help="検査するファイルまたはディレクトリ")
    p.add_argument("--strict", action="store_true", help="裸の数字列もエラーにする")
    p.add_argument("--exclude", action="append", default=[], help="除外するパス（複数指定可）")
    p.add_argument("--message-file", type=Path, default=None, help="コミットメッセージのファイル")
    _add_denylist_arg(p)
    p.set_defaults(func=cmd_redact_check)

    p = sub.add_parser("validate", help="document の検証（第1部 §9）")
    p.add_argument("paths", nargs="*", help="検証する JSON またはディレクトリ")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("bean-check", help="元帳の検査（bean-check を呼ぶ）")
    p.add_argument("--main", default="ledger/main.beancount", help="元帳の入口ファイル")
    p.set_defaults(func=cmd_bean_check)

    p = sub.add_parser("check-public-safe", help="公開リポジトリの安全性検査（第13部 §6.2）")
    p.add_argument("--root", default=".", help="リポジトリのルート")
    p.add_argument("--exclude", action="append", default=[], help="除外するパス（複数指定可）")
    _add_denylist_arg(p)
    p.set_defaults(func=cmd_check_public_safe)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
