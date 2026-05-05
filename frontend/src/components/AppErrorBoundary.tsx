import { Component, type ErrorInfo, type ReactNode } from "react";

const RECOVERY_STORAGE_KEYS = [
  "legal-ai-platform-chat-sessions-v3",
  "legal-ai-platform-chat-map-v2",
  "legal-ai-editor-draft-seed-v1",
];

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  error: Error | null;
  componentStack: string;
}

export default class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { error: null, componentStack: "" };

  static getDerivedStateFromError(error: Error): Partial<AppErrorBoundaryState> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[AppErrorBoundary] Render failed:", error.message);
    console.error(info.componentStack);
    this.setState({ componentStack: info.componentStack ?? "" });
  }

  private softReset = () => {
    this.setState({ error: null, componentStack: "" });
  };

  private recoverWorkspace = () => {
    for (const key of RECOVERY_STORAGE_KEYS) {
      window.localStorage.removeItem(key);
      window.sessionStorage.removeItem(key);
    }
    window.location.assign("/dashboard");
  };

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <main className="app-crash-shell">
        <section className="app-crash-card" role="alert">
          <p className="app-crash-eyebrow">Workspace recovery</p>
          <h1>The interface hit a bad cached response.</h1>
          <p>
            Your login and project data are safe. This clears only local chat/editor cache and reloads the routed
            workspace.
          </p>
          <code>{this.state.error.message || "Render error"}</code>
          {import.meta.env.DEV && this.state.componentStack && (
            <pre className="app-crash-stack">{this.state.componentStack}</pre>
          )}
          <div className="app-crash-actions">
            <button type="button" onClick={this.softReset}>
              Try again
            </button>
            <button type="button" onClick={() => window.location.reload()}>
              Reload
            </button>
            <button type="button" className="primary" onClick={this.recoverWorkspace}>
              Clear local cache
            </button>
          </div>
        </section>
      </main>
    );
  }
}
