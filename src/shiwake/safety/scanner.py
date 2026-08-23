"""機密文字列の検査（第1部 §11 S4 / 第13部 §6.1）。

設計上の要点は「誤検知を出さないこと」に置いている。
帳簿には7桁・12桁の金額が普通に現れるので、裸の数字を無条件に弾く実装は
警告だらけになり、やがて誰も見なくなって**検査が死ぬ**。
それは検査が無いのと同じなので、次の3段に分けている。

  1. 高信頼シグネチャ  文脈なしでエラーにしてよいもの（Luhn を通るカード番号など）
  2. 文脈つき          近くにキーワードがあるときだけエラー（マイナンバーなど）
  3. 裸の数字列        既定は warning。--strict でエラー

加えて、構造化ファイル（.json / .yaml）では
**引用符の中にある数字だけ**を 3 の対象にする。金額は数値として書かれるため。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath

from .denylist import Denylist
from .findings import Finding, Severity, mask, mask_fully

IGNORE_MARKER = "redact-check: ignore"

#: 走査しないディレクトリ。生成物や依存の中を見ても意味がない
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        "dist",
        "build",
    }
)

#: 「引用符の外の数字は数値である」と言い切れる拡張子。
#: 帳簿には7桁・12桁の金額が普通に出るので、ここを弾かないと警告だらけになり
#: 検査そのものが無視されるようになる。それは検査が無いのと同じ。
TYPED_SUFFIXES = frozenset(
    {
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".lock",
        ".ini",
        ".cfg",
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".rb",
        ".java",
        ".sh",
        ".sql",
        ".csv",
        ".tsv",
        ".beancount",
    }
)

#: ドキュメントで使うために予約されているドメイン（誤検知にしない）
RESERVED_EMAIL_DOMAINS = re.compile(
    r"(?:^|\.)(?:example\.(?:com|net|org)|test|invalid|example|localhost)$", re.IGNORECASE
)

_QUOTED = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")
_HEX_RUN = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])")
_DIGIT_RUN = re.compile(r"(?<!\d)\d+(?!\d)")
_CARD_CANDIDATE = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE = re.compile(r"(?<![\d-])(?:\+81[- ]?\d{1,4}|0\d{1,4})[- ]\d{1,4}[- ]\d{4}(?![\d-])")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_POSTAL = re.compile(r"〒?\s*(?<!\d)\d{3}-\d{4}(?!\d)")
_ADDRESS_CTX = re.compile(
    r"(?:都|道|府|県|市|区|町|村|丁目|番地|[0-9０-９]+番|[0-9０-９]+号|マンション|アパート|ビル)"
)
_TOKENS = re.compile(
    r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
)

_MY_NUMBER_CTX = re.compile(
    r"(?:マイナンバー|個人番号|my[_ -]?number|individual[_ -]?number)", re.IGNORECASE
)
_PENSION_CTX = re.compile(r"(?:基礎年金番号|年金番号|pension[_ -]?number)", re.IGNORECASE)
_INSURANCE_CTX = re.compile(
    r"(?:雇用保険(?:被保険者)?番号|employment[_ -]?insurance)", re.IGNORECASE
)

_PENSION_NUMBER = re.compile(r"(?<!\d)\d{4}-?\d{6}(?!\d)")
_INSURANCE_NUMBER = re.compile(r"(?<!\d)\d{4}-?\d{6}-?\d(?!\d)")

_ACCOUNT_KEY = re.compile(
    r"[\"']?(?P<key>[\w぀-ヿ一-鿿]*"
    r"(?:bank[_ ]?account|account[_ ]?(?:no|number)|口座番号|口座)"
    r"[\w぀-ヿ一-鿿]*)[\"']?\s*[:=]\s*[\"'](?P<val>[^\"']*)[\"']",
    re.IGNORECASE,
)
_LAST4_KEY = re.compile(r"last[_ ]?4|下4桁|下四桁", re.IGNORECASE)


def _looks_like_timestamp(digits: str) -> bool:
    """日時として読める数字列か。

    ★スキャナやカメラが付けるファイル名は YYYYMMDDhhmmss の形になり、
      14桁なので Luhn 候補の桁数に入る。そして**偶然 Luhn を通ることがある**。
      実際に取り込みの記録で当たり、コミットできなくなった。

    日付として成立するかを見て、成立するならカード番号とはみなさない。
    """
    if len(digits) not in (8, 12, 14):
        return False
    year = int(digits[:4])
    if not (1900 <= year <= 2200):
        return False
    month, day = int(digits[4:6]), int(digits[6:8])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    if len(digits) >= 12:
        hour, minute = int(digits[8:10]), int(digits[10:12])
        if not (hour <= 23 and minute <= 59):
            return False
    return not (len(digits) == 14 and int(digits[12:14]) > 59)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _spans(pattern: re.Pattern[str], line: str) -> list[tuple[int, int]]:
    return [m.span() for m in pattern.finditer(line)]


def _inside(span: tuple[int, int], spans: Iterable[tuple[int, int]]) -> bool:
    return any(s <= span[0] and span[1] <= e for s, e in spans)


def _overlaps(span: tuple[int, int], spans: Iterable[tuple[int, int]]) -> bool:
    return any(span[0] < e and s < span[1] for s, e in spans)


def _looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


class Scanner:
    """機密文字列を探す。見つけたものを出力しないことが要件の一部。"""

    def __init__(
        self,
        denylist: Denylist | None = None,
        strict: bool = False,
        exclude: Iterable[str] = (),
    ) -> None:
        self.denylist = denylist
        self.strict = strict
        self.exclude = tuple(exclude)

    def is_excluded(self, path: Path | str) -> bool:
        """検査対象から外すパスか。

        事務処理規程のように、実名・住所が入っているのが正しい文書がある
        （第2部 §2.1、第13部 §7）。除外は設定に明示させる。
        """
        text = str(path)
        parts = PurePosixPath(text.replace("\\", "/"))
        return any(
            parts.match(pattern) or pattern.rstrip("/") in parts.parts for pattern in self.exclude
        )

    # ── 入口 ────────────────────────────────────────────

    def scan_text(self, text: str, path: str = "<text>") -> list[Finding]:
        # 拡張子が不明なものは、取りこぼさない側（散文扱い）に倒す
        typed = Path(path).suffix.lower() in TYPED_SUFFIXES
        findings: list[Finding] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if IGNORE_MARKER in line:
                continue
            findings.extend(self._scan_line(line, lineno, path, typed))
        return sorted(findings)

    def scan_file(self, path: Path) -> list[Finding]:
        if self.is_excluded(path):
            return []
        data = path.read_bytes()
        findings: list[Finding] = []
        findings.extend(self._scan_path_name(path))
        if _looks_binary(data):
            return sorted(findings)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return sorted(findings)
        findings.extend(self.scan_text(text, path=str(path)))
        return sorted(findings)

    def scan_paths(self, paths: Iterable[Path]) -> list[Finding]:
        findings: list[Finding] = []
        for path in _walk(paths):
            findings.extend(self.scan_file(path))
        return sorted(findings)

    def scan_commit_message(self, message: str) -> list[Finding]:
        """第13部 §6.3 — コミットメッセージからも固有名詞は漏れる。"""
        return self.scan_text(message, path="<commit-message>")

    # ── 実体 ────────────────────────────────────────────

    def _scan_path_name(self, path: Path) -> list[Finding]:
        if not self.denylist:
            return []
        hits = self.denylist.find(str(path))
        return [
            Finding(
                path=str(path),
                line=0,
                rule="denylist_path",
                severity="error",
                message="ファイル名またはパスに固有名詞が含まれています",
                excerpt=mask_fully(hit),
            )
            for hit in hits
        ]

    def _scan_line(self, line: str, lineno: int, path: str, typed: bool) -> list[Finding]:
        findings: list[Finding] = []
        claimed: list[tuple[int, int]] = []

        def add(
            rule: str, severity: Severity, message: str, excerpt: str, span: tuple[int, int]
        ) -> None:
            findings.append(
                Finding(
                    path=path,
                    line=lineno,
                    rule=rule,
                    severity=severity,
                    message=message,
                    excerpt=excerpt,
                )
            )
            claimed.append(span)

        hex_runs = _spans(_HEX_RUN, line)
        quoted = _spans(_QUOTED, line)

        # ── 1. 高信頼シグネチャ ──────────────────────────
        for m in _PRIVATE_KEY.finditer(line):
            add("private_key", "error", "秘密鍵が含まれています", "<PEM ヘッダ>", m.span())

        for m in _TOKENS.finditer(line):
            add("api_token", "error", "API トークンらしき文字列", mask(m.group()), m.span())

        for m in _CARD_CANDIDATE.finditer(line):
            raw = m.group()
            digits = re.sub(r"[ -]", "", raw)
            if not (13 <= len(digits) <= 19) or len(set(digits)) == 1:
                continue
            if _inside(m.span(), hex_runs) or not _luhn_ok(digits):
                continue
            if _looks_like_timestamp(digits):
                continue  # 日時のファイル名。カード番号ではない
            add("card_number", "error", "カード番号（Luhn 検査を通過）", mask(raw), m.span())

        for m in _EMAIL.finditer(line):
            if RESERVED_EMAIL_DOMAINS.search(m.group(1)):
                continue
            add("email", "error", "メールアドレス", mask(m.group()), m.span())

        for m in _PHONE.finditer(line):
            if _overlaps(m.span(), claimed):
                continue
            add("phone", "error", "電話番号", mask(m.group()), m.span())

        # ── 2. 文脈つき ────────────────────────────────
        if _MY_NUMBER_CTX.search(line):
            for m in _DIGIT_RUN.finditer(line):
                if len(m.group()) == 12 and not _inside(m.span(), hex_runs):
                    add("my_number", "error", "マイナンバーらしき12桁", mask(m.group()), m.span())

        if _PENSION_CTX.search(line):
            for m in _PENSION_NUMBER.finditer(line):
                add("pension_number", "error", "基礎年金番号らしき番号", mask(m.group()), m.span())

        if _INSURANCE_CTX.search(line):
            for m in _INSURANCE_NUMBER.finditer(line):
                add(
                    "employment_insurance",
                    "error",
                    "雇用保険番号らしき番号",
                    mask(m.group()),
                    m.span(),
                )

        for m in _POSTAL.finditer(line):
            if _overlaps(m.span(), claimed) or not _ADDRESS_CTX.search(line):
                continue
            add("postal_address", "error", "郵便番号と住所", mask(m.group().strip()), m.span())

        for m in _ACCOUNT_KEY.finditer(line):
            if _LAST4_KEY.search(m.group("key")):
                continue  # 下4桁のみの保持は仕様上ゆるされている（第1部 §5）
            value = m.group("val")
            if len(re.sub(r"\D", "", value)) >= 5:
                add("bank_account", "error", "口座番号らしき値", mask(value), m.span())

        # ── 3. 裸の数字列（既定は warning）──────────────
        severity: Severity = "error" if self.strict else "warning"
        for m in _DIGIT_RUN.finditer(line):
            run = m.group()
            if len(run) not in (7, 12):
                continue
            if _inside(m.span(), hex_runs) or _overlaps(m.span(), claimed):
                continue
            if typed and not _inside(m.span(), quoted):
                continue  # 数値リテラル＝金額。弾かない
            if _looks_like_timestamp(run):
                continue  # 日時。番号ではない
            rule = f"bare_digits_{len(run)}"
            label = "口座番号" if len(run) == 7 else "マイナンバー"
            add(rule, severity, f"文脈のない{len(run)}桁（{label}の可能性）", mask(run), m.span())

        # ── 名前ベースの層 ──────────────────────────────
        if self.denylist:
            # ★ハッシュの中は見ない。下4桁のような短い数字は、
            #   sha256 の中に偶然含まれる（前後が英字なので数字境界も抜ける）。
            #   実際にロックファイルで当たり、コミットできなくなった。
            searchable = _HEX_RUN.sub("", line) if hex_runs else line
            for hit in self.denylist.find(searchable):
                findings.append(
                    Finding(
                        path=path,
                        line=lineno,
                        rule="denylist",
                        severity="error",
                        message="固有名詞が含まれています",
                        excerpt=mask_fully(hit),
                    )
                )

        return findings


def _walk(paths: Iterable[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and not SKIP_DIRS & set(child.parts):
                    yield child
        elif path.is_file():
            yield path
