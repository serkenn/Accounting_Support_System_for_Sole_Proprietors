/**
 * 概要（第3部 §8.1）。
 *
 * ★数字を先に出す。グラフは補助。
 *   中央寄せのヒーローも、KPI カードの横並びも作らない（§2.1）。
 */
import { Link } from "react-router-dom";
import { FigureCell } from "../components/ext/FigureCell";
import { Empty, LoadError, Loading, Section } from "../components/ext/Section";
import { Table, Td, Th, TotalRow } from "../components/ext/Table";
import { CategoryChart } from "../components/ext/CategoryChart";
import { ErrorBoundary } from "../components/ext/ErrorBoundary";
import {
  type Attention,
  type Category,
  type MonthlySummary,
  loadAttention,
  loadCategories,
  loadSummary,
} from "../lib/data";
import { formatMonth } from "../lib/format";
import { useAsync, useMeta, useScope } from "../lib/state";

export function Overview() {
  const [scope] = useScope();
  const { meta } = useMeta();
  const summary = useAsync<{ monthly: MonthlySummary[] }>(() => loadSummary(scope), [scope]);
  const categories = useAsync<{ months: Record<string, Category[]> }>(
    () => loadCategories(scope),
    [scope],
  );
  const attention = useAsync<Attention>(loadAttention, []);

  const month = meta?.latest_month ?? "";
  const monthly = summary.value?.monthly ?? [];
  const current = monthly.find((m) => m.month === month);
  const cats = categories.value?.months[month] ?? [];

  return (
    <>
      <h2 className="text-std-28B-150">
        {month ? `${formatMonth(month)}の収支` : "収支"}
      </h2>

      {summary.error && <LoadError message={summary.error} />}
      {summary.loading && <Loading />}

      {current && (
        <Table caption={`${formatMonth(month)}の収入と支出`}>
          <tbody>
            <tr>
              <Td>収入</Td>
              <Td numeric>
                <FigureCell value={current.income} />
              </Td>
            </tr>
            <tr>
              <Td>支出</Td>
              <Td numeric>
                <FigureCell value={-current.expense} />
              </Td>
            </tr>
          </tbody>
          <tfoot>
            <TotalRow>
              <Td>差引</Td>
              <Td numeric>
                <FigureCell value={current.net} />
              </Td>
            </TotalRow>
          </tfoot>
        </Table>
      )}

      <Section title="カテゴリ別支出">
        {cats.length === 0 ? (
          <Empty>
            この月の支出はまだありません。領収書を撮影するか、カード明細を取り込んでください。
          </Empty>
        ) : (
          <>
            <Table caption="カテゴリ別の支出">
              <thead>
                <tr>
                  <Th>費目</Th>
                  <Th>区分</Th>
                  <Th numeric>支出（円）</Th>
                  <Th numeric>割合</Th>
                </tr>
              </thead>
              <tbody>
                {cats.map((c) => (
                  <tr key={`${c.namespace}:${c.category}`}>
                    <Td>{c.category}</Td>
                    <Td>{c.namespace === "business" ? "事業" : "家計"}</Td>
                    <Td numeric>
                      <FigureCell value={c.amount} absolute />
                    </Td>
                    <Td numeric>
                      <span className="font-num tabular-nums">
                        {(c.ratio * 100).toFixed(1)}%
                      </span>
                    </Td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <TotalRow>
                  <Td>合計</Td>
                  <Td />
                  <Td numeric>
                    <FigureCell value={cats.reduce((s, c) => s + c.amount, 0)} absolute />
                  </Td>
                  <Td />
                </TotalRow>
              </tfoot>
            </Table>
            {/* 数字が先、絵は後（第3部 §8.1）。
                グラフが落ちても数字は残るように閉じ込める */}
            <ErrorBoundary label="グラフ">
              <CategoryChart categories={cats} />
            </ErrorBoundary>
          </>
        )}
      </Section>

      <Section title="対応が必要なもの">
        {attention.value ? (
          <Table caption="対応が必要なもの">
            <tbody>
              <tr>
                <Td>
                  <Link to="/review" className="text-blue-900 underline">
                    要レビュー
                  </Link>
                </Td>
                <Td numeric>
                  <span className="font-num tabular-nums">
                    {attention.value.needs_review.count}
                  </span>
                  件
                </Td>
              </tr>
              <tr>
                <Td>明細が届いていない領収書</Td>
                <Td numeric>
                  <span className="font-num tabular-nums">{attention.value.pending.count}</span>件
                </Td>
              </tr>
            </tbody>
          </Table>
        ) : (
          <Loading />
        )}
      </Section>

      <Section title="12か月の推移">
        {monthly.length === 0 ? (
          <Empty>まだ記録がありません。</Empty>
        ) : (
          <Table caption="月別の収入・支出・差引">
            <thead>
              <tr>
                <Th>月</Th>
                <Th numeric>収入（円）</Th>
                <Th numeric>支出（円）</Th>
                <Th numeric>差引（円）</Th>
              </tr>
            </thead>
            <tbody>
              {monthly.slice(-12).map((m) => (
                <tr key={m.month}>
                  <Td>
                    <span className="font-num">{m.month}</span>
                  </Td>
                  <Td numeric>
                    <FigureCell value={m.income} />
                  </Td>
                  <Td numeric>
                    <FigureCell value={m.expense} absolute />
                  </Td>
                  <Td numeric>
                    <FigureCell value={m.net} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Section>
    </>
  );
}
