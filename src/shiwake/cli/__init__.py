"""shiwake のコマンドライン入口。

Phase 0.5 の時点では安全性の検査だけを提供する。
取り込み・元帳生成などは各フェーズで追加する。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from shiwake import config as cfg
from shiwake import validate as vd
from shiwake.ingest import Manifest, ingest
from shiwake.ingest.manifest import MANIFEST_NAME
from shiwake.ledger import bean_check, load_postings
from shiwake.ledger.check import BeanCheckMissingError
from shiwake.ledger.query import BeanQueryMissingError
from shiwake.safety import Denylist, Scanner
from shiwake.safety import public_safe as ps
from shiwake.safety.data_repo import check_no_app_code
from shiwake.scopes import load_scopes
from shiwake.tax import check_mapping_coverage, load_mapping


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


def cmd_scope_check(args: argparse.Namespace) -> int:
    """所得区分と名前空間の検査（第5部 §11 / 第10部 §8）。"""
    rules_path = Path(args.rules)
    if not rules_path.is_file():
        print(f"ERROR   {rules_path} がありません", file=sys.stderr)
        return 1
    scopes = load_scopes(rules_path)

    try:
        postings = load_postings(Path(args.main))
    except BeanQueryMissingError as e:
        print(f"ERROR   {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"ERROR   元帳が見つかりません: {e}", file=sys.stderr)
        return 1

    accounts = {p.account for p in postings}
    issues = scopes.check_classification(accounts)
    issues.extend(scopes.check_crossings(postings))
    issues.extend(scopes.check_invariant(postings))

    # 決算書への対応づけ。抜けていると P/L から黙って落ちる（第2部 §7.2）
    mapping_path = Path(args.mapping)
    if mapping_path.is_file():
        issues.extend(check_mapping_coverage(accounts, load_mapping(mapping_path)))
    else:
        print(f"NOTE    {mapping_path} がないため決算書の対応づけは検査しません", file=sys.stderr)

    for i in issues:
        print(i.format(), file=sys.stderr)

    errors = [i for i in issues if i.severity == "error"]
    print(
        f"\nscope-check: {len(postings)} posting / error {len(errors)} 件",
        file=sys.stderr,
    )
    return 1 if errors else 0


def cmd_import(args: argparse.Namespace) -> int:
    """inbox の中身を originals へ移す（第9部 §3.3）。

    数十件をまとめて処理する前提なので、1件の失敗で止めない。
    """
    try:
        conf = cfg.load()
    except cfg.ConfigError as e:
        print(f"ERROR   {e}", file=sys.stderr)
        return 1

    paths = conf.paths
    if not paths.inbox.is_dir():
        print(f"NOTE    {paths.inbox} がありません。取り込むものはありません。", file=sys.stderr)
        return 0

    def progress(index: int, total: int, name: str) -> None:
        print(f"  {index}/{total} 処理中: {name}", file=sys.stderr)

    result = ingest(
        inbox=paths.inbox,
        files=paths.files,
        manifest=Manifest(paths.root / MANIFEST_NAME),
        dry_run=args.dry_run,
        on_progress=progress if not args.quiet else None,
    )

    print("", file=sys.stderr)
    if args.dry_run:
        print("（--dry-run のため、何も移動していません）", file=sys.stderr)
    print(result.summary(), file=sys.stderr)

    review = [i for i in result.succeeded if i.needs_review]
    if review:
        print("", file=sys.stderr)
        print("  紙か電子かを確定できなかったもの:", file=sys.stderr)
        for item in review:
            print(f"    {item.source_name}  → {item.origin}（推定）", file=sys.stderr)
        print(
            "    inbox/paper/ か inbox/electronic/ に置くと確定します。",
            file=sys.stderr,
        )

    for failure in result.failed:
        print(f"\nFAILED  {failure.source_name}: {failure.reason}", file=sys.stderr)

    return 1 if result.failed else 0


def cmd_check_data_repo(args: argparse.Namespace) -> int:
    """データリポジトリにアプリのコードが無いことを確かめる（第13部 §0）。

    分離の前提は「非公開側にコードが1行も無い」こと。
    無ければ誤って公開側へ push する経路が存在しない。
    作業ディレクトリを間違えるだけで崩れるので、機械で止める。
    """
    problems = check_no_app_code(Path(args.root), allow=args.allow)
    for p in problems:
        print(p.format(), file=sys.stderr)
    print(f"\ncheck-data-repo: {len(problems)} 件", file=sys.stderr)
    return 1 if problems else 0


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

    p = sub.add_parser("import", help="inbox の中身を原本として取り込む（第9部 §3）")
    p.add_argument("--dry-run", action="store_true", help="何が起きるかだけを見る")
    p.add_argument("--quiet", action="store_true", help="進捗を出さない")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("validate", help="document の検証（第1部 §9）")
    p.add_argument("paths", nargs="*", help="検証する JSON またはディレクトリ")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("bean-check", help="元帳の検査（bean-check を呼ぶ）")
    p.add_argument("--main", default="ledger/main.beancount", help="元帳の入口ファイル")
    p.set_defaults(func=cmd_bean_check)

    p = sub.add_parser("scope-check", help="所得区分と名前空間の検査（第5部 §11）")
    p.add_argument("--main", default="ledger/main.beancount", help="元帳の入口ファイル")
    p.add_argument("--rules", default="rules/scopes.yaml", help="範囲と規則の定義")
    p.add_argument("--mapping", default="rules/aoiro_mapping.yaml", help="決算書へのマッピング")
    p.set_defaults(func=cmd_scope_check)

    p = sub.add_parser(
        "check-data-repo", help="データ側にアプリのコードが無いかの検査（第13部 §0）"
    )
    p.add_argument("--root", default=".", help="データリポジトリのルート")
    p.add_argument("--allow", action="append", default=[], help="例外にするパス")
    p.set_defaults(func=cmd_check_data_repo)

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
