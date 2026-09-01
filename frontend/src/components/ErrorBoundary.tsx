import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Last-resort guard for a render-time crash in the routed pages. A lazy
 *  chunk that fails to load (network error, code-split bundle gone stale)
 *  or a component throwing during render would otherwise blank the pane
 *  with no recourse. We show the message + a reload button so the user can
 *  recover without restarting the app. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, _info: unknown): void {
    // Keep the error visible in devtools; the fallback below is the UI.
    console.error("ErrorBoundary caught a render error:", error);
  }

  private reset = (): void => {
    this.setState({ error: null });
    window.location.reload();
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error === null) return this.props.children;
    return (
      <div className="flex h-full w-full items-center justify-center bg-bg-base p-6">
        <div className="max-w-md rounded-2xl border border-border/80 bg-bg-card p-6 text-center shadow-card">
          <p className="text-sm font-bold text-fg-base">Something went wrong</p>
          <p className="mt-2 break-words text-xs text-danger leading-relaxed">
            {error.message || String(error)}
          </p>
          <button
            type="button"
            onClick={this.reset}
            className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-accent-fg hover:bg-accent-hover transition-colors shadow-xs active:scale-95"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
