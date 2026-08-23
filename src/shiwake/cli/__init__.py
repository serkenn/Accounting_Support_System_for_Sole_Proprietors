"""shiwake のコマンドライン入口。

Phase 0.5 の時点では安全性の検査だけを提供する。
取り込み・元帳生成などは各フェーズで追加する。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from shiwake import config as cfg
from shiwake import validate as vd
from shiwake.ingest import Manifest, ingest
from shiwake.ingest.manifest import MANIFEST_NAME
from shiwake.ledger import (
    bean_check,
    find_candidates,
    load_categories,
    load_links,
    load_merchants,
    load_postings,
    save_links,
)
from shiwake.ledger.check import BeanCheckMissingError
from shiwake.ledger.documents import load_month, load_skipped
from shiwake.ledger.query import BeanQueryMissingError
from shiwake.ledger.settlement import load_settlement_accounts
from shiwake.rules_check import check_accounts
from shiwake.safety import Denylist, Scanner
from shiwake.safety import public_safe as ps
from shiwake.safety.data_repo import check_no_app_code
from shiwake.safety.pinning import check_pins
from shiwake.scopes import load_scopes
from shiwake.tax import check_mapping_coverage, load_mapping
from shiwake.web import build_web_data
from shiwake.web.labels import load_labels
from shiwake.web.read_ledger import load_ledger_postings


def _add_denylist_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--denylist",
        type=Path,
        default=None,
        help="固有名詞の一覧ファイル。未指定なら既定の置き場を探す",
    )


def cmd_redact_check(args: argparse.Namespace) -> int:
    """機密文字列の検査（第1部 §11 S4 / 第13部 §6.1）。

    ★名前ベースの層（デノイリスト）は「公開側に名前を出さない」ための道具。
      データリポジトリは、その名前が**正当に存在する場所**なので、
      そこで名前検査を掛けるのは道具の使い方が違う。
      口座マスタに銀行名が書けなくなってしまう。

      データ側で効かせるのはパターン層（口座番号・カード番号・マイナンバー）と
      gitleaks。公開側へ出さないことは pre-push が担う。
    """
    denylist = None if args.no_denylist else Denylist.discover(args.denylist)
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

    if denylist is None:
        print(
            "NOTE    名前ベースの検査は無効にしています（--no-denylist）。",
            file=sys.stderr,
        )
    elif not denylist:
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
    root = Path(args.root)
    problems = check_no_app_code(root, allow=args.allow)
    for p in problems:
        print(p.format(), file=sys.stderr)

    # ★ピンが追従になっていないか（第13部 §4・§12）。
    #   人が忘れると静かに壊れるので、ここで一緒に見る。
    pins = check_pins(root / "pyproject.toml")
    for pin in pins:
        print(pin.format(), file=sys.stderr)

    total = len(problems) + len(pins)
    print(f"\ncheck-data-repo: {total} 件", file=sys.stderr)
    return 1 if total else 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    """領収書とカード明細行の突合（第1部 §6）。

    ★候補を出すだけ。**自動確定しない。**
    """
    month = args.month
    root = Path(".")
    merchants = load_merchants(root / "rules" / "merchants.yaml")
    receipts, card_lines, receipt_accounts = load_month(root / "documents", month)
    links_path = root / "links" / f"{month}.json"
    links = load_links(links_path)

    found = find_candidates(receipts, card_lines, merchants, links.linked_keys())

    print(f"突合  {month}", file=sys.stderr)
    print(f"  確定できる候補   {len(found.confident)} 件", file=sys.stderr)
    print(f"  要確認（複数候補）{len(found.ambiguous)} 件", file=sys.stderr)
    print(f"  領収書のみ       {len(found.unmatched_receipts)} 件", file=sys.stderr)
    print(f"  明細のみ         {len(found.unmatched_card_lines)} 件", file=sys.stderr)

    for doc_id, cands in found.ambiguous.items():
        print(f"\n  {doc_id} の候補:", file=sys.stderr)
        for c in cands:
            print(
                f"    {c.card_line_key}  一致度 {c.name_score:.2f} 日付差 {c.date_diff}日",
                file=sys.stderr,
            )
        print("    → どれか選んでください。自動では決めません。", file=sys.stderr)

    if args.apply and found.confident:
        from shiwake.ledger import Links

        merged = Links(month=links.month or month, links=dict(links.links))
        for c in found.confident:
            merged.links.setdefault(c.receipt_doc_id, c.card_line_key)
        save_links(links_path, merged)
        print(f"\n  {len(found.confident)} 件を {links_path} に確定しました", file=sys.stderr)
    elif found.confident:
        print("\n  --apply を付けると確定します（既定は確定しません）", file=sys.stderr)

    return 0


def cmd_build_ledger(args: argparse.Namespace) -> int:
    """documents + links → Beancount（第1部 §6）。

    分類できない取引があれば止まる。「その他」に落として先に進まない。
    """
    from shiwake.ledger import build_month

    month = args.month
    root = Path(".")
    merchants = load_merchants(root / "rules" / "merchants.yaml")
    categorizer = load_categories(root / "rules" / "categories.yaml", merchants)
    receipts, card_lines, receipt_accounts = load_month(root / "documents", month)
    links = load_links(root / "links" / f"{month}.json")

    result = build_month(
        receipts,
        card_lines,
        links,
        categorizer,
        receipt_accounts=receipt_accounts,
        settlement_accounts=load_settlement_accounts(root / "rules" / "accounts.yaml"),
    )

    for issue in result.issues:
        print(issue.format(), file=sys.stderr)

    # ★金額が読めず元帳に入れなかったものを黙って落とさない。
    #   落とすと、費用が過小のまま誰も気づかない。
    skipped = load_skipped(root / "documents", month)
    for doc_id in skipped:
        print(
            f"WARNING  [build] {doc_id}: 合計が読み取れていないため元帳に入れていません。"
            "原本を見て金額を入れてください",
            file=sys.stderr,
        )

    if result.errors:
        print(
            f"\nbuild-ledger: error {len(result.errors)} 件。元帳を出力しません。",
            file=sys.stderr,
        )
        return 1

    out = root / "ledger" / "generated" / f"{month}.beancount"
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        ";; このファイルは生成物です。手で編集しません。\n"
        ";; 直すときは documents/ か rules/ を直して再生成します。"
    )
    out.write_text(result.render(header), encoding="utf-8")
    print(
        f"build-ledger: {len(result.transactions)} 件の仕訳を {out} に出力しました", file=sys.stderr
    )
    return 0


def cmd_build_web_data(args: argparse.Namespace) -> int:
    """元帳 → Web 用の静的 JSON（第1部 §10）。

    画面に出る数字はここで全部確定させる。ブラウザ側で集計し直さない。
    """
    import subprocess
    from datetime import datetime

    main = Path(args.main)
    rules = Path(args.rules)
    if not rules.is_file():
        print(f"ERROR   {rules} がありません", file=sys.stderr)
        return 1

    try:
        postings = load_ledger_postings(main)
    except (BeanQueryMissingError, FileNotFoundError) as e:
        print(f"ERROR   {e}", file=sys.stderr)
        return 1

    documents = []
    docs_dir = Path(args.documents)
    if docs_dir.is_dir():
        for path in sorted(docs_dir.rglob("*.json")):
            documents.append(json.loads(path.read_text(encoding="utf-8")))

    # ★紙に刷ったときリポジトリの状態と紐づけるため（第3部 §10）
    commit = ""
    with contextlib.suppress(subprocess.SubprocessError, FileNotFoundError):
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()

    data = build_web_data(
        postings=postings,
        documents=documents,
        scopes=load_scopes(rules),
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        commit=commit,
        note=args.note,
        labels=load_labels(rules.parent / "labels.yaml"),
    )

    # ★表示名の無い科目があれば止める。黙って英語を出さない。
    if data.unlabelled_accounts:
        for account in data.unlabelled_accounts:
            print(f"ERROR   [labels] {account}: 画面に出す名前がありません", file=sys.stderr)
        print(
            "\nbuild-web-data: 表示名の無い科目があります。"
            "rules/labels.yaml に足すか、公開側の既定に足してください。",
            file=sys.stderr,
        )
        return 1

    written = data.write(Path(args.out))
    print(f"build-web-data: {len(written)} ファイルを {args.out} に出力しました", file=sys.stderr)
    for path in written:
        print(f"  {path.name}", file=sys.stderr)
    return 0


def cmd_check_rules(args: argparse.Namespace) -> int:
    """口座・カードのマスタの検査（第1部 D5 / 第4部 §1）。"""
    issues = check_accounts(Path(args.accounts))
    for i in issues:
        print(i.format(), file=sys.stderr)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    print(f"\ncheck-rules: error {len(errors)} 件 / warning {len(warnings)} 件", file=sys.stderr)
    return 1 if errors else 0


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
    p.add_argument(
        "--no-denylist",
        action="store_true",
        help="名前ベースの検査を行わない（名前が正当に存在するリポジトリで使う）",
    )
    _add_denylist_arg(p)
    p.set_defaults(func=cmd_redact_check)

    p = sub.add_parser("import", help="inbox の中身を原本として取り込む（第9部 §3）")
    p.add_argument("--dry-run", action="store_true", help="何が起きるかだけを見る")
    p.add_argument("--quiet", action="store_true", help="進捗を出さない")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("reconcile", help="領収書とカード明細行の突合（第1部 §6）")
    p.add_argument("month", help="対象の年月（YYYY-MM）")
    p.add_argument("--apply", action="store_true", help="候補が1つだけのものを確定する")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("build-ledger", help="documents と links から元帳を生成する")
    p.add_argument("month", help="対象の年月（YYYY-MM）")
    p.set_defaults(func=cmd_build_ledger)

    p = sub.add_parser("build-web-data", help="元帳から Web 用の静的 JSON を作る（第1部 §10）")
    p.add_argument("--main", default="ledger/main.beancount", help="元帳の入口")
    p.add_argument("--documents", default="documents", help="documents ディレクトリ")
    p.add_argument("--rules", default="rules/scopes.yaml", help="ビューの範囲")
    p.add_argument("--out", default="web/public/data", help="出力先")
    p.add_argument("--note", default=None, help="meta.json に添える注記")
    p.set_defaults(func=cmd_build_web_data)

    p = sub.add_parser("check-rules", help="口座・カードのマスタの検査（第1部 D5）")
    p.add_argument("--accounts", default="rules/accounts.yaml", help="口座マスタ")
    p.set_defaults(func=cmd_check_rules)

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
