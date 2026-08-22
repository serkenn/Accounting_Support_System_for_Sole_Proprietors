/**
 * 証憑（第8部 §4.3）。
 *
 * ★この画面の日常の用途は鑑賞ではなく**検算**。
 *   きれいに大きく見せることより、
 *   **原本と抽出結果が同時に見えて数字を突き合わせられる**ことを優先する。
 *
 *   デスクトップは左右、モバイルは上下。どちらでも同時に見える。
 */
import { useParams } from "react-router-dom";
import { FigureCell, StatusTag } from "../components/ext/FigureCell";
import { LoadError, Loading } from "../components/ext/Section";
import { Table, Td, Th, TotalRow } from "../components/ext/Table";
import {
  type DocumentSummary,
  derivedUrl,
  loadDocuments,
  originalUrl,
} from "../lib/data";
import { formatDate, formatPercent } from "../lib/format";
import { useAsync } from "../lib/state";

export function Evidence() {
  const { docId } = useParams();
  const { value, error, loading } = useAsync<{ documents: DocumentSummary[] }>(loadDocuments, []);
  const doc = value?.documents.find((d) => d.doc_id === docId) ?? null;

  if (error) return <LoadError message={error} />;
  if (loading) return <Loading />;
  if (!doc) {
    return (
      <p role="alert" className="text-std-16N-170 text-red-800">
        証憑 <span className="font-num">{docId}</span> が見つかりません。
      </p>
    );
  }

  const view = derivedUrl(doc.original_ref);
  const download = originalUrl(doc.original_ref, doc.original_ext);
  const taxTotal = (doc.tax_breakdown ?? []).reduce(
    (s, t) => s + t.taxable_amount + t.tax_amount,
    0,
  );

  return (
    <>
      <h2 className="text-std-28B-150">{doc.issuer || "証憑"}</h2>
      <p className="mt-1 text-std-16N-170 text-solid-gray-600">
        <span className="font-num">{doc.doc_id}</span>
      </p>

      {doc.needs_review && (
        <p className="mt-2 text-std-16N-170 text-red-800">
          <StatusTag kind="review">要レビュー</StatusTag>{" "}
          {doc.review_reason || "理由が記録されていません"}
        </p>
      )}

      {/* ★並置。デスクトップは左右、モバイルは上下 */}
      <div className="mt-4 flex flex-col gap-6 desktop-admin:flex-row">
        <div className="min-w-0 flex-1">
          <h3 className="border-b-2 border-solid-gray-600 pb-1 text-std-20B-150">原本</h3>
          {doc.derivative_error ? (
            <p className="mt-3 text-std-16N-170 text-red-800">
              プレビューを生成できませんでした。原本は保存されています。
              <br />
              下のリンクからダウンロードして確認してください。
            </p>
          ) : view ? (
            <img
              src={view}
              alt={`${doc.issuer ?? "証憑"}の原本`}
              className="mt-3 w-full border border-solid-gray-300 object-contain"
            />
          ) : (
            <p className="mt-3 text-std-16N-170 text-solid-gray-600">原本がありません。</p>
          )}
          {download && (
            <p className="no-print mt-2">
              {/* 原本はインライン表示しない。ダウンロードのみ（第8部 §6） */}
              <a href={download} download className="text-std-16N-170 text-blue-900 underline">
                原本をダウンロードする
              </a>
            </p>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <h3 className="border-b-2 border-solid-gray-600 pb-1 text-std-20B-150">抽出結果</h3>
          <div className="mt-3">
            <Table caption="原本から読み取った値">
              <tbody>
                <tr>
                  <Td>発行者</Td>
                  <Td>{doc.issuer || "—"}</Td>
                </tr>
                <tr>
                  <Td>日付</Td>
                  <Td>
                    <span className="font-num">{formatDate(doc.issued_at)}</span>
                  </Td>
                </tr>
                <tr>
                  <Td>区分</Td>
                  <Td>{doc.origin === "paper" ? "紙を撮影" : "電子で受け取り"}</Td>
                </tr>
                <tr>
                  <Td>合計</Td>
                  <Td numeric>
                    <FigureCell value={doc.total} />
                  </Td>
                </tr>
              </tbody>
            </Table>

            {doc.tax_breakdown && doc.tax_breakdown.length > 0 && (
              <div className="mt-4">
                <Table caption="税率別の内訳">
                  <thead>
                    <tr>
                      <Th>税率</Th>
                      <Th numeric>対象（円）</Th>
                      <Th numeric>税額（円）</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.tax_breakdown.map((t) => (
                      <tr key={t.rate}>
                        <Td>
                          <span className="font-num">{formatPercent(t.rate)}</span>
                        </Td>
                        <Td numeric>
                          <FigureCell value={t.taxable_amount} />
                        </Td>
                        <Td numeric>
                          <FigureCell value={t.tax_amount} />
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <TotalRow>
                      <Td>合計</Td>
                      <Td numeric colSpan={2}>
                        <FigureCell value={taxTotal} />
                      </Td>
                    </TotalRow>
                  </tfoot>
                </Table>
                {doc.total !== null && taxTotal !== doc.total && (
                  <p className="mt-2 text-std-16N-170 text-red-800">
                    税率別内訳の合計が合計額と一致しません。原本を確認してください。
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
