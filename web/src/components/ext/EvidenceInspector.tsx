/**
 * 根拠インスペクタ（第3部 §7）。
 *
 * ★このアプリで唯一「凝る」ところ。他は徹底して地味にする。
 *
 * 画面上のどの金額からでも、その数字の出どころを**1本の鎖として**辿れる。
 * モーダルの入れ子にしない。全段を同時に見せる。
 *
 *   選択した金額
 *     ├─ 仕訳    どの科目にいくら
 *     ├─ 証憑    どの原本から来たか
 *     └─ 原本    実物の画像
 */
import { Link } from "react-router-dom";
import { type DocumentSummary, type Transaction, derivedUrl, loadDocuments } from "../../lib/data";
import { formatDate } from "../../lib/format";
import { useAsync } from "../../lib/state";
import { FigureCell } from "./FigureCell";

export function EvidenceInspector({
  transaction,
  onClose,
}: {
  transaction: Transaction;
  onClose: () => void;
}) {
  const { value } = useAsync<{ documents: DocumentSummary[] }>(loadDocuments, []);
  const doc = value?.documents.find((d) => d.doc_id === transaction.doc_id) ?? null;
  const image = derivedUrl(doc?.original_ref ?? null);

  return (
    <aside
      aria-label="根拠"
      className="w-[360px] shrink-0 border-l border-solid-gray-300 pl-4 print:w-full print:border-0 print:pl-0"
    >
      <div className="flex items-baseline justify-between border-b-2 border-solid-gray-600 pb-1">
        <h2 className="text-std-20B-150">根拠</h2>
        <button
          type="button"
          onClick={onClose}
          className="no-print text-std-16N-170 text-blue-900 underline"
        >
          閉じる
        </button>
      </div>

      <Step label="仕訳">
        <p className="text-std-16N-170">
          <span className="font-num">{formatDate(transaction.date)}</span>{" "}
          {transaction.payee}
        </p>
        <table className="mt-2 w-full border-collapse text-std-16N-170">
          <caption className="sr-only">仕訳の内訳</caption>
          <tbody>
            {transaction.postings.map((p) => (
              <tr key={p.account}>
                <td className="border-b border-solid-gray-300 py-1 pr-2 align-baseline">
                  {p.account}
                </td>
                <td className="border-b border-solid-gray-300 py-1 text-right align-baseline">
                  <FigureCell value={p.amount} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {transaction.card_line && (
          <p className="mt-2 text-std-16N-170 text-solid-gray-600">
            カード明細行 <span className="font-num">{transaction.card_line}</span>
          </p>
        )}
      </Step>

      <Step label="証憑">
        {doc ? (
          <>
            <p className="text-std-16N-170">
              <Link to={`/evidence/${doc.doc_id}`} className="text-blue-900 underline">
                <span className="font-num">{doc.doc_id}</span>
              </Link>
            </p>
            <p className="mt-1 text-std-16N-170 text-solid-gray-600">
              {doc.origin === "paper" ? "紙を撮影" : "電子で受け取り"} ／ 発行者{" "}
              {doc.issuer || "—"}
            </p>
          </>
        ) : (
          <p className="text-std-16N-170 text-solid-gray-600">
            この仕訳には証憑が紐づいていません。カード明細だけから作られた仕訳です。
          </p>
        )}
      </Step>

      <Step label="原本">
        {doc?.derivative_error ? (
          <p className="text-std-16N-170 text-red-800">
            プレビューを生成できませんでした。原本は保存されています。
          </p>
        ) : image ? (
          <>
            <img
              src={image}
              alt={`${doc?.issuer ?? "証憑"}の原本`}
              loading="lazy"
              className="max-h-[400px] w-full border border-solid-gray-300 object-contain"
            />
            <p className="mt-1 text-std-16N-170 text-solid-gray-600">
              <span className="font-num">
                {(doc?.original_ref ?? "").replace("sha256:", "").slice(0, 12)}
              </span>
            </p>
          </>
        ) : (
          <p className="text-std-16N-170 text-solid-gray-600">原本がありません。</p>
        )}
      </Step>
    </aside>
  );
}

/** 鎖の1段。既定で開いた状態にする（第3部 §7）。 */
function Step({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="mt-4 border-l-2 border-solid-gray-300 pl-3">
      <h3 className="text-std-16B-170 text-solid-gray-700">{label}</h3>
      <div className="mt-1">{children}</div>
    </section>
  );
}
