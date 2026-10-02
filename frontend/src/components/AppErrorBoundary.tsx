import { AlertTriangle, RotateCcw } from "lucide-react";
import { Component, Fragment } from "react";
import type { ErrorInfo, ReactNode } from "react";

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
  error: Error | null;
  retryKey: number;
};

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, retryKey: 0 };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, retryKey: 0 };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("页面渲染失败", error, info.componentStack);
  }

  reset = () => {
    this.setState((current) => ({ hasError: false, error: null, retryKey: current.retryKey + 1 }));
  };

  reload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) return <Fragment key={this.state.retryKey}>{this.props.children}</Fragment>;

    return (
      <section className="panel loadingPanel appErrorPanel" role="alert">
        <AlertTriangle size={28} />
        <h2>当前页面暂时无法显示</h2>
        <p>页面加载遇到异常，请重试或刷新应用。</p>
        <div className="appErrorActions">
          <button className="refreshRetryButton" onClick={this.reset}>
            <RotateCcw size={14} />
            重试当前页面
          </button>
          <button className="refreshRetryButton secondaryRefreshButton" onClick={this.reload}>
            刷新应用
          </button>
        </div>
      </section>
    );
  }
}
