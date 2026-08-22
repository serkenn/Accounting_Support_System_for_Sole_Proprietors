/**
 * 静的 JSON の読み込み（第1部 §8 — バックエンドを持たない）。
 *
 * ★画面側で集計し直さない。ここで読んだ値をそのまま出す。
 */

export type Scope = "household" | "business";

export type Meta = {
  schema_version: number;
  generated_at: string;
  commit: string;
  months: string[];
  latest_month: string;
  scopes: Record<Scope, { label: string }>;
  _note?: string;
};

export type MonthlySummary = {
  month: string;
  income: number;
  expense: number;
  net: number;
  /** 支出のうち事業のために出た分。同額が事業への持分に変わっている */
  business_share: number;
};
export type Category = { namespace: string; category: string; amount: number; ratio: number };
export type PostingRow = { account: string; amount: number };
export type Transaction = {
  id: string;
  date: string;
  payee: string;
  narration: string;
  account: string;
  amount: number;
  doc_id: string | null;
  card_line: string | null;
  pending: boolean;
  postings: PostingRow[];
};
export type AccountBalance = { account: string; balance: number };
export type Attention = {
  needs_review: { count: number; doc_ids: string[] };
  pending: { count: number; transaction_ids: string[] };
  receipts_awaiting_statement: { count: number };
};
export type DocumentSummary = {
  doc_id: string;
  type: string;
  origin: string;
  needs_review: boolean;
  review_reason: string | null;
  issuer: string | null;
  issued_at: string | null;
  total: number | null;
  tax_breakdown: { rate: number; taxable_amount: number; tax_amount: number }[] | null;
  original_ref: string | null;
  original_ext: string | null;
  page_count: number;
  derivative_error: string | null;
};

const BASE = "/data";

async function get<T>(name: string): Promise<T> {
  const res = await fetch(`${BASE}/${name}`);
  if (!res.ok) {
    // ★黙って空を返さない。読めなかったことを画面に出す（第3部 §11）
    throw new Error(`${name} を読み込めませんでした（${res.status}）`);
  }
  return (await res.json()) as T;
}

export const loadMeta = () => get<Meta>("meta.json");
export const loadSummary = (scope: Scope) =>
  get<{ monthly: MonthlySummary[] }>(`summary-${scope}.json`);
export const loadCategories = (scope: Scope) =>
  get<{ months: Record<string, Category[]> }>(`categories-${scope}.json`);
export const loadTransactions = (scope: Scope) =>
  get<{ transactions: Transaction[] }>(`transactions-${scope}.json`);
export const loadAccounts = (scope: Scope) =>
  get<{ accounts: AccountBalance[] }>(`accounts-${scope}.json`);
export const loadAttention = () => get<Attention>("attention.json");
export const loadDocuments = () => get<{ documents: DocumentSummary[] }>("documents.json");

/** 原本の派生画像のパス（第8部 §2.2）。 */
export function derivedUrl(originalRef: string | null, name = "view.webp"): string | null {
  if (!originalRef) return null;
  const sha = originalRef.replace(/^sha256:/, "");
  if (!/^[0-9a-f]{64}$/.test(sha)) return null;
  // 派生のファイル名も、こちらが決めたものだけを通す
  if (!/^(thumb|view|p[0-9]{3})\.webp$/.test(name)) return null;
  return `/files/derived/${sha.slice(0, 2)}/${sha}/${name}`;
}

/**
 * 原本そのもの。ダウンロード専用（インライン表示しない・第8部 §6）。
 *
 * ★拡張子も検証する。検証しないと `../` を混ぜてパスを抜けられる。
 *   値は取り込み処理が magic bytes から決めたものだが、
 *   JSON を経由して来る以上、ここでも確かめる。
 */
export function originalUrl(originalRef: string | null, ext: string | null): string | null {
  if (!originalRef || !ext) return null;
  const sha = originalRef.replace(/^sha256:/, "");
  if (!/^[0-9a-f]{64}$/.test(sha)) return null;
  if (!/^[a-z0-9]{1,8}$/.test(ext)) return null;
  return `/files/originals/${sha.slice(0, 2)}/${sha}.${ext}`;
}
