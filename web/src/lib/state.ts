/** 画面の状態。バックエンドを持たないので、全部ブラウザ内で完結する。 */
import { useEffect, useState } from "react";
import { type Meta, type Scope, loadMeta } from "./data";

const SCOPE_KEY = "shiwake.scope";

export function useScope(): [Scope, (s: Scope) => void] {
  const [scope, set] = useState<Scope>(() => {
    const saved = typeof localStorage !== "undefined" ? localStorage.getItem(SCOPE_KEY) : null;
    return saved === "business" ? "business" : "household";
  });
  useEffect(() => {
    try {
      localStorage.setItem(SCOPE_KEY, scope);
    } catch {
      // 保存できなくても表示は続ける
    }
  }, [scope]);
  return [scope, set];
}

/** 読み込みの状態。★読めなかったことを黙って隠さない（第3部 §11）。 */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    load()
      .then((v) => live && setValue(v))
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { value, error, loading };
}

export function useMeta() {
  const { value, error } = useAsync<Meta>(loadMeta, []);
  return { meta: value, error };
}
