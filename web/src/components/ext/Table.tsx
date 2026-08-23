/**
 * 表の部品（第3部 §4.3）。
 *
 * ★囲みや影ではなく、**罫線の階層**で構造を示す。
 *
 *   細罫（1px 淡グレー）  明細行の区切り
 *   太罫（2px 濃グレー）  見出し行と本体の区切り
 *   二重罫              合計行の上（帳簿の「〆」の意味を持つ）
 *
 * 二重罫は「ここが合計である」という情報を持つので、装飾として他に使わない。
 */
import type { ReactNode } from "react";

export function Table({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-std-16N-170">
        {/* スクリーンリーダ向け。視覚的には見出しが担う */}
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}

export function Th({
  children,
  numeric = false,
  scope = "col",
}: {
  children: ReactNode;
  numeric?: boolean;
  scope?: "col" | "row";
}) {
  return (
    <th
      scope={scope}
      className={`border-b-2 border-solid-gray-600 px-3 py-2 text-std-16B-170 text-solid-gray-900 first:pl-0 last:pr-0 ${
        numeric ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  numeric = false,
  className = "",
  colSpan,
}: {
  children?: ReactNode;
  numeric?: boolean;
  className?: string;
  colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={`border-b border-solid-gray-300 px-3 py-2 align-baseline first:pl-0 last:pr-0 ${
        numeric ? "text-right" : "text-left"
      } ${className}`}
    >
      {children}
    </td>
  );
}

/**
 * 合計行。上に二重罫を引く（帳簿の「〆」）。
 * ★これは「ここが合計である」という情報。装飾として他の場所に使わない。
 */
export function TotalRow({ children }: { children: ReactNode }) {
  return (
    <tr className="border-t-2 border-double border-solid-gray-600 text-std-16B-170">{children}</tr>
  );
}
