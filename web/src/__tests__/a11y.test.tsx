/**
 * アクセシビリティの床（第3部 §12・§14）。
 *
 * ★DADS は JIS X 8341-3 / WCAG 2.1 AA 準拠を目標にしている。それを下げない。
 *   違反 0 件を必須にする。
 */
import { render, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "../components/ext/AppShell";
import { Detail } from "../screens/Detail";
import { Evidence } from "../screens/Evidence";
import { Overview } from "../screens/Overview";
import { Review } from "../screens/Review";

const SHA = "sha256:" + "a1b2c3d4".repeat(8);

const DATA: Record<string, unknown> = {
  "meta.json": {
    schema_version: 1,
    generated_at: "2026-08-22T22:00:00+09:00",
    commit: "abc1234",
    months: ["2026-07"],
    latest_month: "2026-07",
    scopes: { household: { label: "家計" }, business: { label: "事業" } },
  },
  "summary-household.json": {
    monthly: [{ month: "2026-07", income: 284000, expense: 162340, net: 121660 }],
  },
  "categories-household.json": {
    months: { "2026-07": [{ namespace: "personal", category: "Food", amount: 48200, ratio: 1 }] },
  },
  "transactions-household.json": {
    transactions: [
      {
        id: "t1", date: "2026-07-14", payee: "サンプルストア", narration: "",
        account: "Expenses:Personal:Food:Groceries", amount: 1234,
        doc_id: "doc_2026-07-14_sample_a1b2c3", card_line: null, pending: true,
        postings: [{ account: "Expenses:Personal:Food:Groceries", amount: 1234 }],
      },
    ],
  },
  "accounts-household.json": { accounts: [] },
  "attention.json": {
    needs_review: { count: 1, doc_ids: [] },
    pending: { count: 1, transaction_ids: [] },
    receipts_awaiting_statement: { count: 0 },
  },
  "documents.json": {
    documents: [
      {
        doc_id: "doc_2026-07-14_sample_a1b2c3", type: "receipt", origin: "paper",
        needs_review: true, review_reason: "読み取れません", issuer: "サンプルストア",
        issued_at: "2026-07-14T12:00:00+09:00", total: 1234,
        tax_breakdown: [{ rate: 0.1, taxable_amount: 1122, tax_amount: 112 }],
        original_ref: SHA, original_ext: "jpg", page_count: 1, derivative_error: null,
      },
    ],
  },
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const name = String(url).split("/").pop()!;
      if (!(name in DATA)) return { ok: false, status: 404 } as Response;
      return { ok: true, json: async () => DATA[name] } as Response;
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

async function auditAt(path: string) {
  const { container } = render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<Overview />} />
          <Route path="transactions" element={<Detail />} />
          <Route path="review" element={<Review />} />
          <Route path="evidence/:docId" element={<Evidence />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  // データの読み込みが終わってから検査する
  await waitFor(() => expect(container.querySelectorAll("table").length).toBeGreaterThan(0));
  const results = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
  });
  return results.violations;
}

describe("axe-core（違反 0 件が必須）", () => {
  it("概要", async () => {
    const v = await auditAt("/");
    expect(v.map((x) => `${x.id}: ${x.help}`)).toEqual([]);
  });

  it("明細", async () => {
    const v = await auditAt("/transactions");
    expect(v.map((x) => `${x.id}: ${x.help}`)).toEqual([]);
  });

  it("要レビュー", async () => {
    const v = await auditAt("/review");
    expect(v.map((x) => `${x.id}: ${x.help}`)).toEqual([]);
  });

  it("証憑", async () => {
    const v = await auditAt("/evidence/doc_2026-07-14_sample_a1b2c3");
    expect(v.map((x) => `${x.id}: ${x.help}`)).toEqual([]);
  });
});
