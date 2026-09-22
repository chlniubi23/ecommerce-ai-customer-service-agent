"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches errors thrown inside the AI assistant panel and shows a friendly
 * recovery UI instead of a white screen. Particularly useful when a backend
 * API returns unexpected shapes that crash a render path.
 */
export class AssistantErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[AssistantErrorBoundary]", error, info.componentStack);
  }

  reset = () => this.setState({ error: null });

  override render() {
    if (this.state.error) {
      return (
        <div className="fixed bottom-5 right-5 z-50 w-80 overflow-hidden rounded-2xl border border-line bg-elevated shadow-[0_18px_48px_rgba(0,0,0,0.5)] backdrop-blur">
          <div className="h-[3px] bg-accent-gradient" />
          <div className="p-5">
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-danger/15 text-danger">
                <AlertTriangle className="h-4 w-4" />
              </span>
              <div>
                <p className="text-sm font-black text-primary">助手遇到了问题</p>
                <p className="mt-1 text-xs leading-5 text-secondary">
                  界面渲染出错，请点击重新加载。如持续出现，刷新页面即可恢复。
                </p>
                <button
                  type="button"
                  onClick={this.reset}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-bold text-white transition hover:bg-accent-hover"
                >
                  <RefreshCcw className="h-3 w-3" />
                  重新加载助手
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
