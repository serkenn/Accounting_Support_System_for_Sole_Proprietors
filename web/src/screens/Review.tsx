/**
 * 要レビュー（第1部 §10-4）。
 *
 * ★低信頼のデータを集計から外さず、ここで目立たせる（第1部 P5）。
 */
import { Link } from "react-router-dom";
import { FigureCell, StatusTag } from "../components/ext/FigureCell";
import { Empty, LoadError, Loading } from "../components/ext/Section";
import { Table, Td, Th } from "../components/ext/Table";
import { type DocumentSummary, loadDocuments } from "../lib/data";
import { formatDate } from "../lib/format";
import { useAsync } from "../lib/state";

export function Review() {
  const { value, error, loading } = useAsync<{ documents: DocumentSummary[] }>(loadDocuments, []);
  const rows = (value?.documents ?? []).filter((d) => d.needs_review);

  return (
    <>
      <h2 className="text-std-28B-150">要レビュー</h2>
      <p className="mt-2 text-std-16N-170 text-solid-gray-700">
        読み取れなかった値や、確認が要る証憑です。原本と並べて確かめてください。
      </p>

      {error && <LoadError message={error} />}
      {loading && <Loading />}

      {!loading && rows.length === 0 ? (
        <Empty>確認が必要なものはありません。</Empty>
      ) : (
        <div className="mt-4">
          <Table caption="確認が必要な証憑">
            <thead>
              <tr>
                <Th>日付</Th>
                <Th>発行者</Th>
                <Th numeric>合計（円）</Th>
                <Th>理由</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.doc_id}>
                  <Td>
                    <span className="font-num">{formatDate(d.issued_at)}</span>
                  </Td>
                  <Td>
                    <Link to={`/evidence/${d.doc_id}`} className="text-blue-900 underline">
                      {d.issuer || d.doc_id}
                    </Link>
                  </Td>
                  <Td numeric>
                    <FigureCell value={d.total} />
                  </Td>
                  <Td>
                    <StatusTag kind="review">要レビュー</StatusTag>{" "}
                    {d.review_reason || "理由が記録されていません"}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </>
  );
}
