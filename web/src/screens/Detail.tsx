/**
 * 明細（第3部 §8.2）。
 *
 * 表の直下に**絞り込み結果の合計行（二重罫）**を常に出す。
 * 行を選ぶと根拠インスペクタが開く（画面遷移しない）。
 */
import { useMemo, useState } from "react";
import { EvidenceInspector } from "../components/ext/EvidenceInspector";
import { FigureCell, StatusTag } from "../components/ext/FigureCell";
import { Empty, LoadError, Loading } from "../components/ext/Section";
import { Table, Td, Th, TotalRow } from "../components/ext/Table";
import { type Transaction, loadTransactions } from "../lib/data";
import { formatDate } from "../lib/format";
import { useAsync, useScope } from "../lib/state";

export function Detail() {
  const [scope] = useScope();
  const { value, error, loading } = useAsync<{ transactions: Transaction[] }>(
    () => loadTransactions(scope),
    [scope],
  );
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Transaction | null>(null);

  const rows = useMemo(() => {
    const all = value?.transactions ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter(
      (t) =>
        t.payee.toLowerCase().includes(q) ||
        t.account.toLowerCase().includes(q) ||
        t.date.includes(q),
    );
  }, [value, query]);

  const total = rows.reduce((s, t) => s + t.amount, 0);

  return (
    <div className="flex gap-6">
      <div className="min-w-0 flex-1">
        <h2 className="text-std-28B-150">明細</h2>

        <div className="no-print mt-4">
          <label className="block">
            <span className="text-std-16N-170 text-solid-gray-700">
              日付・取引先・勘定科目で絞り込む
            </span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="mt-1 w-full border border-solid-gray-600 px-2 py-1 text-std-16N-170 desktop:w-96"
            />
          </label>
        </div>

        {error && <LoadError message={error} />}
        {loading && <Loading />}

        {!loading && rows.length === 0 ? (
          <Empty>
            該当する取引がありません。絞り込みを変えるか、証憑を取り込んでください。
          </Empty>
        ) : (
          <div className="mt-4">
            <Table caption="取引の明細">
              <thead>
                <tr>
                  <Th>日付</Th>
                  <Th>取引先</Th>
                  <Th>勘定科目</Th>
                  <Th numeric>金額（円）</Th>
                  <Th>状態</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.id}>
                    <Td>
                      <span className="font-num">{formatDate(t.date)}</span>
                    </Td>
                    <Td>
                      <button
                        type="button"
                        onClick={() => setSelected(t)}
                        className="text-left text-blue-900 underline"
                      >
                        {t.payee || "（取引先なし）"}
                      </button>
                    </Td>
                    <Td className="text-solid-gray-700">{t.account}</Td>
                    <Td numeric>
                      <FigureCell value={t.amount} />
                    </Td>
                    <Td>{t.pending && <StatusTag kind="pending">明細未着</StatusTag>}</Td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                {/* ★絞り込み結果の合計は常に出す（第3部 §8.2） */}
                <TotalRow>
                  <Td>合計</Td>
                  <Td>{rows.length}件</Td>
                  <Td />
                  <Td numeric>
                    <FigureCell value={total} />
                  </Td>
                  <Td />
                </TotalRow>
              </tfoot>
            </Table>
          </div>
        )}
      </div>

      {/* ★本文を押しのけて開く。オーバーレイしない。
          本文と根拠を同時に見るのが目的だから（第3部 §6.2） */}
      {selected && (
        <EvidenceInspector transaction={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
