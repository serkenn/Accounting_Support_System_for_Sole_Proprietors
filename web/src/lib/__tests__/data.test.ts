import { describe, expect, it } from "vitest";
import { derivedUrl, originalUrl } from "../data";

describe("原本と派生の URL（第8部 §2.2）", () => {
  const sha = "sha256:" + "a1b2c3d4".repeat(8);

  it("コンテンツアドレスのパスを組み立てる", () => {
    expect(derivedUrl(sha)).toBe(`/files/derived/a1/${"a1b2c3d4".repeat(8)}/view.webp`);
  });

  it("サムネも同じディレクトリから引く", () => {
    expect(derivedUrl(sha, "thumb.webp")).toContain("/thumb.webp");
  });

  it("原本は拡張子つきのパス", () => {
    expect(originalUrl(sha, "heic")).toBe(`/files/originals/a1/${"a1b2c3d4".repeat(8)}.heic`);
  });

  it("不正なハッシュは null（パスを組み立てない）", () => {
    // ★外部由来の値でパスを作らせない
    expect(derivedUrl("sha256:../../etc/passwd")).toBeNull();
    expect(derivedUrl("not-a-hash")).toBeNull();
    expect(originalUrl(sha, "../evil")).toBeNull();
  });

  it("値が無ければ null", () => {
    expect(derivedUrl(null)).toBeNull();
    expect(originalUrl(sha, null)).toBeNull();
  });
});

describe("パスの組み立てを外部の値に任せない", () => {
  const sha = "sha256:" + "a1b2c3d4".repeat(8);

  it("派生のファイル名は既知のものだけ通す", () => {
    expect(derivedUrl(sha, "view.webp")).not.toBeNull();
    expect(derivedUrl(sha, "p001.webp")).not.toBeNull();
    expect(derivedUrl(sha, "../../secret")).toBeNull();
    expect(derivedUrl(sha, "evil.svg")).toBeNull();
  });

  it("拡張子は英数字のみ", () => {
    expect(originalUrl(sha, "pdf")).not.toBeNull();
    expect(originalUrl(sha, "../evil")).toBeNull();
    expect(originalUrl(sha, "svg/../x")).toBeNull();
  });
});
