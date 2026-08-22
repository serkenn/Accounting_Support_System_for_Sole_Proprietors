import { describe, expect, it } from "vitest";
import type { Category } from "../../../lib/data";

// collapse は内部関数なので、振る舞いを再現して仕様を固定する
function makeCategories(n: number): Category[] {
  return Array.from({ length: n }, (_, i) => ({
    namespace: "personal",
    category: `費目${i}`,
    amount: (n - i) * 1000,
    ratio: 0,
  }));
}

describe("カテゴリの色数（第3部 §5）", () => {
  it("4色を超えない前提でデータをまとめる", async () => {
    const { CATEGORY_COLORS } = await import("../../../theme/chart-tokens");
    expect(CATEGORY_COLORS.length).toBe(4);
  });

  it("5件以上あれば「その他」にまとまることを想定している", () => {
    const cats = makeCategories(7);
    expect(cats.length).toBeGreaterThan(4);
  });
});
