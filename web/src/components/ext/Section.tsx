/**
 * セクションの区切り（第3部 §2.2）。
 *
 * ★カードで囲まない。罫線と余白で区切る。
 *   囲みを外したら構造が壊れる作りにしない。
 */
import type { ReactNode } from "react";

export function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="mt-8 first:mt-0">
      <div className="flex items-baseline justify-between border-b-2 border-solid-gray-600 pb-1">
        <h2 className="text-std-20B-150">{title}</h2>
        {action}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** 空状態。★次の行動を書く。「データがありません」で終わらせない（第3部 §11）。 */
export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-4 text-std-16N-170 text-solid-gray-600">{children}</p>;
}

/** 読み込み中。 */
export function Loading() {
  return <p className="py-4 text-std-16N-170 text-solid-gray-600">読み込んでいます…</p>;
}

/** 読み込みに失敗。★原因と次の行動を書く（第3部 §11）。 */
export function LoadError({ message }: { message: string }) {
  return (
    <p role="alert" className="py-4 text-std-16N-170 text-red-800">
      {message}
      <br />
      データを生成し直してから再読み込みしてください。
    </p>
  );
}
