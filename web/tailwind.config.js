import dads from "@digital-go-jp/tailwind-theme-plugin";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // ★DADS のプラグインが提供する値だけを使う。
  //   ここに独自の色・余白・角丸・影を足さない（第3部 §3.3）。
  //   足したくなったら設計を見直す合図。
  theme: {
    extend: {
      fontFamily: {
        // 数字・ID・ハッシュだけ等幅にする（第3部 §4.1）。
        // 桁が縦に揃うことは帳簿では機能要件であって装飾ではない。
        num: ["'Noto Sans Mono'", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [dads],
};
