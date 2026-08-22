/**
 * 描画の失敗を閉じ込める。
 *
 * ★グラフ1つが落ちて画面全体が消えると、**数字が見えなくなる**。
 *   数字が本体でグラフは補助（第3部 §8.1）なので、逆であってはいけない。
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode; label: string };
type State = { failed: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`${this.props.label} の描画に失敗しました`, error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return (
        <p className="py-2 text-std-16N-170 text-solid-gray-600">
          {this.props.label}を表示できませんでした。表の数値は上に出ています。
        </p>
      );
    }
    return this.props.children;
  }
}
