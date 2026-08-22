import { describe, expect, it } from "vitest";
import { AXIS_COLOR, CATEGORY_COLORS, GRID_COLOR, MAX_CATEGORIES, TEXT_COLOR, _read } from "../chart-tokens";

describe("chart tokens", () => {
  it("トークンから実際の値を読めている（フォールバックに落ちていない）", () => {
    // ★パスを間違えるとフォールバックの値が黙って使われる。
    //   そうなると「トークンを使っている」つもりで独自の色を使うことになる。
    expect(_read("Color.Neutral.SolidGray.600", "FALLBACK")).not.toBe("FALLBACK");
    expect(_read("Color.Primitive.Blue.900", "FALLBACK")).not.toBe("FALLBACK");
  });

  it("存在しないパスはフォールバックを返す", () => {
    expect(_read("Color.Nope.Nothing", "FALLBACK")).toBe("FALLBACK");
  });

  it("カテゴリの色は4色まで（第3部 §5）", () => {
    expect(CATEGORY_COLORS).toHaveLength(4);
    expect(MAX_CATEGORIES).toBe(4);
  });

  it("色が重複していない", () => {
    expect(new Set(CATEGORY_COLORS).size).toBe(CATEGORY_COLORS.length);
  });

  it("すべて hex 形式", () => {
    for (const c of [...CATEGORY_COLORS, AXIS_COLOR, GRID_COLOR, TEXT_COLOR]) {
      expect(c).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it("紫〜ネオン系を使っていない（第3部 §2.1）", () => {
    // 紫のプリミティブが混ざっていないこと
    const purple = _read("Color.Primitive.Purple.900", "");
    expect(CATEGORY_COLORS as readonly string[]).not.toContain(purple);
  });
});
