/**
 * 数値表示の規定（第3部 §4.2）。全画面共通・例外なし。
 *
 * ★ここで一度だけ実装し、以降どの画面でもこれを経由する。
 *   金額を素の文字列で組み立てない。組み立てた瞬間に規定が崩れる。
 */

/** 円未満は切り捨て。丸め方向は本来 rules/tax から来る（要決定 D15）。 */
export function toYen(value: number): number {
  return Math.trunc(value);
}

/**
 * 金額。3桁区切り、負数は `△` を前置（日本の会計慣行・決算書と表記を揃える）。
 *
 * ★`-` ではなく `△`。決算書の表記と揃えないと、印刷して並べたときに食い違う。
 */
export function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = toYen(value);
  const body = Math.abs(n).toLocaleString("ja-JP");
  return n < 0 ? `△${body}` : body;
}

/**
 * 支出額そのもの。絶対値で出し、「支出」であることは列見出しで示す。
 * （第3部 §4.2 — 支出額は絶対値、列見出しで明示）
 */
export function formatExpense(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return Math.abs(toYen(value)).toLocaleString("ja-JP");
}

/** 按分率など。小数第2位までのパーセント。 */
export function formatPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined) return "—";
  return `${(ratio * 100).toFixed(2)}%`;
}

/** 電力量など。小数1桁 + 単位は列見出しに。 */
export function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(1);
}

/** 画面の日付は ISO 固定。和暦は帳票出力側で変換する。 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

/** 期間。 */
export function formatPeriod(from: string, to: string): string {
  return `${formatDate(from)} 〜 ${formatDate(to)}`;
}

/** 月の見出し。 */
export function formatMonth(month: string): string {
  const [y, m] = month.split("-");
  return `${y}年${Number(m)}月`;
}

/**
 * ゼロは `0` と出す。`—` にしない。
 * `—` は「未取得・該当なし」の意味なので、ゼロと区別できなくなる。
 */
export function isMissing(value: number | null | undefined): boolean {
  return value === null || value === undefined;
}
