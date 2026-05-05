import React from "react";

interface State {
    hasError: boolean;
    message: string;
    componentStack: string;
}

export class PortalErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
    constructor(props: { children: React.ReactNode }) {
        super(props);
        this.state = { hasError: false, message: "", componentStack: "" };
    }

    static getDerivedStateFromError(error: unknown): Partial<State> {
        return {
            hasError: true,
            message: error instanceof Error ? error.message : "An unexpected error occurred.",
        };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error("[PortalErrorBoundary] Render failed:", error.message);
        console.error(info.componentStack);
        this.setState({ componentStack: info.componentStack ?? "" });
    }

    softReset = () => {
        this.setState({ hasError: false, message: "", componentStack: "" });
    };

    hardRecover = () => {
        localStorage.removeItem("legal-ai-client-portal-token");
        window.location.href = "/auth";
    };

    render() {
        if (this.state.hasError) {
            return (
                <div className="portal-root">
                    <div className="card" style={{ maxWidth: 480, margin: "10vh auto" }}>
                        <p className="eyebrow">Secure Client Workspace</p>
                        <h2>Something went wrong</h2>
                        <p>{this.state.message}</p>
                        {import.meta.env.DEV && this.state.componentStack && (
                            <pre style={{
                                fontSize: "0.72rem",
                                color: "var(--ink-faint)",
                                background: "var(--bg-alt)",
                                borderRadius: 8,
                                padding: "0.75rem",
                                overflowX: "auto",
                                maxHeight: 180,
                                marginTop: "0.75rem",
                            }}>
                                {this.state.componentStack}
                            </pre>
                        )}
                        <div style={{ display: "flex", gap: "0.75rem", marginTop: "1.25rem" }}>
                            <button
                                className="btn"
                                onClick={this.softReset}
                                type="button"
                            >
                                Try again
                            </button>
                            <button
                                className="btn primary"
                                onClick={this.hardRecover}
                                type="button"
                            >
                                Return to sign in
                            </button>
                        </div>
                    </div>
                </div>
            );
        }
        return this.props.children;
    }
}
