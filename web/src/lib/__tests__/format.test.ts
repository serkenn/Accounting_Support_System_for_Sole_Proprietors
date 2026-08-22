import { describe, expect, it } from "vitest";
import {
  formatAmount,
  formatDate,
  formatExpense,
  formatMonth,
  formatPercent,
  formatQuantity,
  isMissing,
} from "../format";

describe("金額（第3部 §4.2）", () => {
  it("3桁区切りにする", () => {
    expect(formatAmount(1234567)).toBe("1,234,567");
  });

  it("負数は △ を前置する（決算書と表記を揃える）", () => {
    // ★ハイフンにしない。印刷して決算書と並べたときに食い違う
    expect(formatAmount(-1234)).toBe("△1,234");
    expect(formatAmount(-1234)).not.toContain("-");
  });

  it("ゼロは 0 と出す。— にしない", () => {
    // — は「未取得・該当なし」の意味。ゼロと区別できなくなる
    expect(formatAmount(0)).toBe("0");
  });

  it("未取得は em ダッシュ", () => {
    expect(formatAmount(null)).toBe("—");
    expect(formatAmount(undefined)).toBe("—");
  });

  it("円未満は切り捨てる", () => {
    expect(formatAmount(1234.9)).toBe("1,234");
  });
});

describe("支出額", () => {
  it("絶対値で出す（列見出しで支出と明示する前提）", () => {
    expect(formatExpense(-9000)).toBe("9,000");
    expect(formatExpense(9000)).toBe("9,000");
  });

  it("未取得は em ダッシュ", () => {
    expect(formatExpense(null)).toBe("—");
  });
});

describe("率・数量", () => {
  it("按分率は小数第2位まで", () => {
    expect(formatPercent(0.42)).toBe("42.00%");
    expect(formatPercent(0.4183)).toBe("41.83%");
  });

  it("電力量は小数1桁", () => {
    expect(formatQuantity(267.94)).toBe("267.9");
  });
});

describe("日付", () => {
  it("画面は ISO 固定", () => {
    expect(formatDate("2026-08-14T19:23:00+09:00")).toBe("2026-08-14");
  });

  it("月の見出し", () => {
    expect(formatMonth("2026-08")).toBe("2026年8月");
  });

  it("未取得は em ダッシュ", () => {
    expect(formatDate(null)).toBe("—");
  });
});

describe("欠測の判定", () => {
  it("ゼロは欠測ではない", () => {
    expect(isMissing(0)).toBe(false);
    expect(isMissing(null)).toBe(true);
  });
});
