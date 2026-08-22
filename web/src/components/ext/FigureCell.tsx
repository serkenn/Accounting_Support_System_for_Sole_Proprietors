/**
 * 金額セル（第3部 §3.4 / §4.2）。
 *
 * ★金額を素の <span> で出さない。必ずここを経由する。
 *   等幅・右揃え・3桁区切り・△ 表記を1箇所で保証するため。
 */
import { formatAmount, formatExpense } from "../../lib/format";

type Props = {
  value: number | null | undefined;
  /** 支出額として絶対値で出すか（列見出しで「支出」と明示する前提） */
  absolute?: boolean;
  /** 推定・見込みの値か。数値の直後にラベルが付く（色だけで示さない） */
  estimated?: boolean;
  className?: string;
};

export function FigureCell({ value, absolute = false, estimated = false, className = "" }: Props) {
  const text = absolute ? formatExpense(value) : formatAmount(value);
  return (
    <span className={`inline-flex items-baseline justify-end gap-1 ${className}`}>
      {/* tabular-nums がないと桁が縦に揃わない。帳簿では機能要件 */}
      <span className="font-num tabular-nums text-right">{text}</span>
      {estimated && <StatusTag kind="estimated">見込み</StatusTag>}
    </span>
  );
}

/**
 * 状態のラベル（第3部 §3.4）。
 * ★色だけで情報を伝えない。必ず文字で書く（§5・印刷対応）。
 */
export function StatusTag({
  kind,
  children,
}: {
  kind: "estimated" | "review" | "pending" | "settled";
  children: React.ReactNode;
}) {
  const tone =
    kind === "review"
      ? "border-red-800 text-red-800"
      : kind === "settled"
        ? "border-solid-gray-420 text-solid-gray-600"
        : "border-solid-gray-600 text-solid-gray-900";
  return (
    <span className={`whitespace-nowrap border px-1 text-std-16N-170 ${tone}`}>[{children}]</span>
  );
}
