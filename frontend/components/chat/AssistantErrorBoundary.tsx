"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

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
        <div className="fixed bottom-5 right-5 z-50 w-80 overflow-hidden rounded-2xl border border-red-100 bg-white shadow-[0_18px_48px_rgba(239,68,68,0.15)]">
          <div className="h-[3px] bg-gradient-to-r from-red-400 to-rose-500" />
          <div className="p-5">
            <div className="flex items-start gap-3">
              <span className="text-2xl">⚠️</span>
              <div>
                <p className="text-sm font-black text-slate-900">助手遇到了问题</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  界面渲染出错，请点击重新加载。如持续出现，刷新页面即可恢复。
                </p>
                <button
                  type="button"
                  onClick={this.reset}
                  className="mt-3 rounded-full bg-slate-900 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-slate-700"
                >
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
