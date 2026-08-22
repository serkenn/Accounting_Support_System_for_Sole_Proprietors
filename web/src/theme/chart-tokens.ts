/**
 * チャートに渡す色（第3部 §3.3 の唯一の例外）。
 *
 * Recharts が CSS 変数を受け付けない箇所があるため、
 * トークンから読んだ値を**ここ1箇所に集約**する。ここ以外に書かない。
 *
 * 第3部 §5 — カテゴリ別の色は4色まで。5つ目以降は「その他」にまとめる。
 */
import tokens from "@digital-go-jp/design-tokens/dist/tokens.js";

type TokenNode = Record<string, unknown>;

function read(path: string, fallback: string): string {
  const parts = path.split(".");
  let node: unknown = (tokens as { default?: TokenNode }).default ?? (tokens as unknown as TokenNode);
  for (const part of parts) {
    if (node && typeof node === "object" && part in (node as object)) {
      node = (node as Record<string, unknown>)[part];
    } else {
      return fallback;
    }
  }
  if (node && typeof node === "object" && "$value" in (node as object)) {
    const value = (node as { $value?: unknown }).$value;
    if (typeof value === "string") return value;
  }
  return fallback;
}

/** カテゴリ別グラフの色。4色まで（第3部 §5）。 */
export const CATEGORY_COLORS = [
  read("Color.Primitive.Blue.900", "#0017C1"),
  read("Color.Neutral.SolidGray.600", "#767676"),
  read("Color.Primitive.Cyan.700", "#008199"),
  read("Color.Neutral.SolidGray.400", "#B3B3B3"),
] as const;

export const AXIS_COLOR = read("Color.Neutral.SolidGray.600", "#767676");
export const GRID_COLOR = read("Color.Neutral.SolidGray.200", "#D8D8D8");
export const TEXT_COLOR = read("Color.Neutral.SolidGray.900", "#1A1A1C");

/** 系列が5つ以上なら「その他」にまとめる（第3部 §5）。 */
export const MAX_CATEGORIES = CATEGORY_COLORS.length;

/** フォールバックに落ちていないかを検査するために公開する。 */
export const _read = read;
