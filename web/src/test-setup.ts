import "@testing-library/jest-dom/vitest";

// jsdom は ResizeObserver を持たない。Recharts の ResponsiveContainer が使う。
// ブラウザには存在するので、テスト環境だけの補い。
if (!("ResizeObserver" in globalThis)) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}
