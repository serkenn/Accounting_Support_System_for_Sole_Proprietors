/**
 * 画面が実際に描画され、規定どおりの数字が出るかを確かめる。
 *
 * 第3部 §14 の受け入れ基準のうち、機械で確かめられるものをここで固定する。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "../../components/ext/AppShell";
import { Detail } from "../Detail";
import { Evidence } from "../Evidence";
import { Overview } from "../Overview";
import { Review } from "../Review";

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
  "summary-business.json": { monthly: [] },
  "categories-household.json": {
    months: {
      "2026-07": [
        { namespace: "personal", category: "Food", amount: 48200, ratio: 0.297 },
        { namespace: "business", category: "Supplies", amount: 12800, ratio: 0.079 },
      ],
    },
  },
  "categories-business.json": { months: {} },
  "transactions-household.json": {
    transactions: [
      {
        id: "t1",
        date: "2026-07-14",
        payee: "サンプルストア",
        narration: "",
        account: "Expenses:Personal:Food:Groceries",
        amount: 1234,
        doc_id: "doc_2026-07-14_sample_a1b2c3",
        card_line: "doc_stmt:L001",
        pending: false,
        postings: [
          { account: "Expenses:Personal:Food:Groceries", amount: 1234 },
          { account: "Liabilities:Personal:CreditCard:Sample", amount: -1234 },
        ],
      },
    ],
  },
  "transactions-business.json": { transactions: [] },
  "accounts-household.json": { accounts: [] },
  "accounts-business.json": { accounts: [] },
  "attention.json": {
    needs_review: { count: 1, doc_ids: ["doc_2026-07-14_sample_a1b2c3"] },
    pending: { count: 2, transaction_ids: [] },
    receipts_awaiting_statement: { count: 0 },
  },
  "documents.json": {
    documents: [
      {
        doc_id: "doc_2026-07-14_sample_a1b2c3",
        type: "receipt",
        origin: "paper",
        needs_review: true,
        review_reason: "合計額が汚れで読み取れません",
        issuer: "サンプルストア",
        issued_at: "2026-07-14T12:00:00+09:00",
        total: 1234,
        tax_breakdown: [{ rate: 0.1, taxable_amount: 1122, tax_amount: 112 }],
        original_ref: SHA,
        original_ext: "jpg",
        page_count: 1,
        derivative_error: null,
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

function renderAt(path: string) {
  return render(
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
}

// ── 概要 ────────────────────────────────────────────────

describe("概要", () => {
  it("収支の数字が出る", async () => {
    renderAt("/");
    // 収入・支出・差引が並ぶ最初の表を見る
    const row = (await screen.findByText("収入")).closest("tr")!;
    expect(within(row).getByText("284,000")).toBeInTheDocument();
    const total = (await screen.findByText("差引")).closest("tr")!;
    expect(within(total).getByText("121,660")).toBeInTheDocument();
  });

  it("支出は △ を前置する（第3部 §4.2）", async () => {
    renderAt("/");
    expect(await screen.findByText("△162,340")).toBeInTheDocument();
  });

  it("カテゴリに区分（事業/家計）が出る", async () => {
    renderAt("/");
    expect(await screen.findByText("Supplies")).toBeInTheDocument();
    expect(await screen.findAllByText("事業")).not.toHaveLength(0);
  });

  it("対応が必要なものの件数が出る", async () => {
    renderAt("/");
    const heading = await screen.findByRole("heading", { name: "対応が必要なもの" });
    const section = heading.closest("section")!;
    expect(within(section).getByText("要レビュー")).toBeInTheDocument();
    expect(within(section).getByText("1")).toBeInTheDocument();
  });
});

// ── 明細 ────────────────────────────────────────────────

describe("明細", () => {
  it("取引が出る", async () => {
    renderAt("/transactions");
    expect(await screen.findByText("サンプルストア")).toBeInTheDocument();
  });

  it("合計行が常に出る（第3部 §8.2）", async () => {
    renderAt("/transactions");
    const foot = (await screen.findByText("合計")).closest("tr")!;
    expect(within(foot).getByText("1件")).toBeInTheDocument();
  });

  it("行を選ぶと根拠が開き、仕訳の全行が見える（第3部 §7）", async () => {
    const { container } = renderAt("/transactions");
    const link = await screen.findByRole("button", { name: "サンプルストア" });
    link.click();
    await waitFor(() => {
      expect(within(container).getByRole("complementary", { name: "根拠" })).toBeInTheDocument();
    });
    const aside = within(container).getByRole("complementary", { name: "根拠" });
    expect(within(aside).getByText("Expenses:Personal:Food:Groceries")).toBeInTheDocument();
    expect(within(aside).getByText("Liabilities:Personal:CreditCard:Sample")).toBeInTheDocument();
  });
});

// ── 要レビュー ──────────────────────────────────────────

describe("要レビュー", () => {
  it("理由が表示される（数値だけを出さない）", async () => {
    renderAt("/review");
    expect(await screen.findByText(/合計額が汚れで読み取れません/)).toBeInTheDocument();
  });
});

// ── 証憑（第8部 §4.3）──────────────────────────────────

describe("証憑", () => {
  it("原本と抽出結果が同時に見える", async () => {
    renderAt("/evidence/doc_2026-07-14_sample_a1b2c3");
    expect(await screen.findByRole("heading", { name: "原本" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "抽出結果" })).toBeInTheDocument();
  });

  it("原本は派生画像を出す（原本そのものはインライン表示しない）", async () => {
    renderAt("/evidence/doc_2026-07-14_sample_a1b2c3");
    const img = (await screen.findByRole("img")) as HTMLImageElement;
    expect(img.src).toContain("/files/derived/");
    expect(img.src).not.toContain("/files/originals/");
  });

  it("原本のダウンロードは attachment 扱いのリンクにする", async () => {
    renderAt("/evidence/doc_2026-07-14_sample_a1b2c3");
    const link = (await screen.findByText("原本をダウンロードする")) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toContain("/files/originals/");
    expect(link.hasAttribute("download")).toBe(true);
  });

  it("見つからない証憑は、その旨を出す", async () => {
    renderAt("/evidence/doc_nope");
    expect(await screen.findByRole("alert")).toHaveTextContent(/見つかりません/);
  });
});

// ── 読み込み失敗を隠さない（第3部 §11）─────────────────

describe("読み込みの失敗", () => {
  it("読めなかったことを画面に出す", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500 }) as Response));
    renderAt("/");
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
  });
});
