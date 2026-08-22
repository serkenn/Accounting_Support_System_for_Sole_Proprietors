/**
 * カテゴリ別支出のグラフ（第3部 §9）。
 *
 * ★Recharts の既定スタイルは全部上書きする。
 *   既定のパレット・角丸ツールチップ・凡例をそのまま出すと、
 *   一目で汎用ダッシュボードの見た目になる。
 *
 * ★グラフを使わない判断も選択肢。ここは横棒1本で、表の補助に徹する。
 */
import { Bar, BarChart, Cell, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { AXIS_COLOR, CATEGORY_COLORS, MAX_CATEGORIES } from "../../theme/chart-tokens";
import type { Category } from "../../lib/data";

type Props = { categories: Category[] };

/** 5つ目以降は「その他」にまとめる（第3部 §5 — 色は4色まで）。 */
function collapse(categories: Category[]): { name: string; amount: number }[] {
  const head = categories.slice(0, MAX_CATEGORIES - 1);
  const tail = categories.slice(MAX_CATEGORIES - 1);
  const rows = head.map((c) => ({ name: c.category, amount: c.amount }));
  if (tail.length > 0) {
    rows.push({ name: "その他", amount: tail.reduce((s, c) => s + c.amount, 0) });
  }
  return rows;
}

export function CategoryChart({ categories }: Props) {
  const rows = collapse(categories);
  if (rows.length === 0) return null;

  return (
    <div className="mt-4" aria-hidden="true">
      {/* 表が本体。グラフは補助なので読み上げ対象から外す */}
      <ResponsiveContainer width="100%" height={rows.length * 36 + 24}>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 0 }}>
          {/* 縦グリッドは引かない。枠でも囲まない（第3部 §9） */}
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="name"
            width={112}
            axisLine={false}
            tickLine={false}
            tick={{ fill: AXIS_COLOR, fontSize: 14 }}
          />
          <Bar dataKey="amount" isAnimationActive={false} barSize={16}>
            {rows.map((row, i) => (
              <Cell key={row.name} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
