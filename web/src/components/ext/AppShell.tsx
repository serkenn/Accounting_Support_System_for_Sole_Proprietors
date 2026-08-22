/**
 * 画面の枠（第3部 §6.2〜6.4）。
 *
 * デスクトップ: ナビは常時表示・固定。ハンバーガーにしない
 *               （1クリックで全画面に届く）
 * モバイル:     下部固定バー。用途を「投入と確認」に絞る
 */
import { NavLink, Outlet } from "react-router-dom";
import { useMeta, useScope } from "../../lib/state";

const NAV = [
  { to: "/", label: "概要", end: true },
  { to: "/transactions", label: "明細" },
  { to: "/review", label: "要レビュー" },
];

function navClass({ isActive }: { isActive: boolean }) {
  return [
    "block border-l-4 px-3 py-2 text-std-16N-170",
    isActive
      ? "border-blue-900 bg-solid-gray-50 text-std-16B-170 text-solid-gray-900"
      : "border-transparent text-solid-gray-700 hover:bg-solid-gray-50",
  ].join(" ");
}

export function AppShell() {
  const { meta, error } = useMeta();
  const [scope, setScope] = useScope();

  return (
    <div className="min-h-screen">
      <header className="no-print border-b-2 border-solid-gray-600">
        <div className="flex flex-wrap items-center gap-4 px-4 py-3">
          <h1 className="text-std-20B-150">家計簿</h1>

          {/* ★タブではなくセグメント切替。常にどちらを見ているかを明示する（第5部 §9.1） */}
          <div
            role="group"
            aria-label="表示する範囲"
            className="flex border border-solid-gray-600"
          >
            {(["household", "business"] as const).map((key) => (
              <button
                key={key}
                type="button"
                aria-pressed={scope === key}
                onClick={() => setScope(key)}
                className={[
                  "px-3 py-1 text-std-16N-170",
                  scope === key
                    ? "bg-solid-gray-900 text-white"
                    : "bg-white text-solid-gray-700",
                ].join(" ")}
              >
                {key === "household" ? "家計" : "事業"}
              </button>
            ))}
          </div>

          {meta && (
            <p className="ml-auto text-std-16N-170 text-solid-gray-600">
              最終更新 {meta.generated_at.slice(0, 16).replace("T", " ")}
            </p>
          )}
        </div>
      </header>

      {error && (
        <p role="alert" className="border-b border-red-800 px-4 py-3 text-red-800">
          {error}
        </p>
      )}

      <div className="flex">
        <nav aria-label="画面" className="no-print hidden w-[200px] shrink-0 border-r border-solid-gray-300 py-4 desktop:block">
          <ul>
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} className={navClass}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <main className="min-w-0 flex-1 px-4 py-6 pb-20 desktop:pb-6">
          <Outlet />
        </main>
      </div>

      {/* モバイルの下部固定バー。項目は4つまで（第3部 §6.4） */}
      <nav
        aria-label="画面（モバイル）"
        className="no-print fixed inset-x-0 bottom-0 border-t-2 border-solid-gray-600 bg-white desktop:hidden"
      >
        <ul className="flex">
          {NAV.map((item) => (
            <li key={item.to} className="flex-1">
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  [
                    // タップターゲット 44px 以上（第3部 §12）
                    "flex min-h-[44px] items-center justify-center py-2 text-std-16N-170",
                    isActive ? "text-std-16B-170 text-blue-900" : "text-solid-gray-700",
                  ].join(" ")
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {meta && (
        <footer className="hidden border-t border-solid-gray-300 px-4 py-2 text-std-16N-170 text-solid-gray-600 print:block">
          {/* ★紙とリポジトリの状態を紐づける（第3部 §10） */}
          出力日時 {new Date().toISOString().slice(0, 16).replace("T", " ")} ／ コミット{" "}
          <span className="font-num">{meta.commit || "—"}</span>
        </footer>
      )}
    </div>
  );
}
