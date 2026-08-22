/**
 * 第3部 §2.1 の禁止事項と §3.3 のトークン規約を機械的に検査する。
 *
 * ★「AI が作った UI」の見た目は、ほぼ決まった要素の組み合わせで発生する。
 *   人の目でレビューし続けるのは無理なので、ここで落とす。
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function sources(dir = SRC): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "__tests__" ? [] : sources(path);
    return /\.(tsx?|css)$/.test(name) ? [path] : [];
  });
}

/**
 * コメントを落とした本文。
 * 規約が縛るのは**画面に出るもの**であって、コードの注釈ではない。
 * コメントまで検査すると、説明のために書いた記号で落ちる。
 */
function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
}

function read(path: string) {
  return {
    path: path.replace(SRC, "src"),
    text: stripComments(readFileSync(path, "utf8")),
  };
}

const FILES = sources().map(read);
const UI = FILES.filter((f) => !f.path.includes("theme/chart-tokens"));

function offenders(pattern: RegExp) {
  return UI.filter((f) => pattern.test(f.text)).map((f) => f.path);
}

describe("禁止事項（第3部 §2.1）", () => {
  it("ドロップシャドウを使わない", () => {
    expect(offenders(/\bshadow-(?!none)/)).toEqual([]);
  });

  it("グラデーションを使わない", () => {
    expect(offenders(/gradient/i)).toEqual([]);
  });

  it("角丸を乱用しない（DADS のトークン外の丸めを作らない）", () => {
    expect(offenders(/rounded-(lg|xl|2xl|3xl|md|sm)\b/)).toEqual([]);
  });

  it("既定の欧文フォントを使わない", () => {
    // 自分で font-family に指定した場合を見る。
    // 依存が持ち込む名前まで拾うと、直しようがないもので落ちる。
    const declared = UI.filter((f) =>
      /font-family[^;]*(Inter|Poppins|Montserrat)/i.test(f.text),
    ).map((f) => f.path);
    expect(declared).toEqual([]);
  });

  it("紫系のアクセントを使わない", () => {
    expect(offenders(/\b(purple|violet|indigo|fuchsia)-\d/)).toEqual([]);
  });

  it("絵文字を置かない", () => {
    // 見出し・ラベル・空状態のどこにも置かない
    // Unicode の Emoji_Presentation と、異体字セレクタ付きの記号を見る。
    // ★や罫線のような「絵文字表示にならない記号」は対象外。
    const emoji = /\p{Emoji_Presentation}|\p{Extended_Pictographic}\uFE0F/u;
    expect(offenders(emoji)).toEqual([]);
  });

  it("意味のないアニメーションを使わない", () => {
    expect(offenders(/\b(animate-(pulse|bounce|spin|ping)|transition-all)\b/)).toEqual([]);
  });
});

describe("トークンの規約（第3部 §3.3）", () => {
  it("hex を直書きしない", () => {
    // chart-tokens.ts だけが例外（フォールバック値を持つ）
    expect(offenders(/#[0-9a-fA-F]{6}\b/)).toEqual([]);
  });

  it("任意の px を書かない", () => {
    // Tailwind の任意値記法 text-[15px] / p-[13px] など。
    // 幅の指定（w-[200px] / w-[360px]）はレイアウトの寸法なので、
    // 使う場合はここに明示的に許す。
    const arbitrary = /\b(?:text|p|m|gap|space|rounded|border)-\[[^\]]+\]/;
    expect(offenders(arbitrary)).toEqual([]);
  });

  it("独自の font-size を定義しない", () => {
    expect(offenders(/font-size\s*:/)).toEqual([]);
  });
});

describe("数値表示（第3部 §4.2）", () => {
  it("金額は FigureCell を経由する", () => {
    // toLocaleString を画面側で直接呼んでいないこと
    const direct = UI.filter(
      (f) => !f.path.includes("lib/format") && /toLocaleString/.test(f.text),
    ).map((f) => f.path);
    expect(direct).toEqual([]);
  });

  it("負数のハイフン表記を画面で作らない", () => {
    // △ は format.ts が付ける。画面で "-" + 金額 を組み立てない
    expect(offenders(/["`]-\$\{/)).toEqual([]);
  });
});

describe("アクセシビリティの床（第3部 §12）", () => {
  it("フォーカスリングを消さない", () => {
    expect(offenders(/outline-none|focus:outline-none/)).toEqual([]);
  });

  it("表に caption を付ける", () => {
    const table = FILES.find((f) => f.path.endsWith("Table.tsx"))!;
    expect(table.text).toContain("<caption");
  });

  it("動きを減らす設定を尊重する", () => {
    const css = FILES.find((f) => f.path.endsWith("index.css"))!;
    expect(css.text).toContain("prefers-reduced-motion");
  });
});

describe("印刷（第3部 §10）", () => {
  it("印刷用スタイルが用意されている", () => {
    const css = FILES.find((f) => f.path.endsWith("index.css"))!;
    expect(css.text).toContain("@media print");
    expect(css.text).toContain("A4");
    // 表の見出しをページまたぎで繰り返す
    expect(css.text).toContain("table-header-group");
  });

  it("ナビや操作ボタンは印刷しない", () => {
    const css = FILES.find((f) => f.path.endsWith("index.css"))!;
    expect(css.text).toContain(".no-print");
  });
});

describe("ダークモードは対象外（第3部 §0）", () => {
  it("ダーク用の指定を書かない", () => {
    expect(offenders(/\bdark:/)).toEqual([]);
  });
});
