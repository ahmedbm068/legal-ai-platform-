import React from "react";
import { clearToken } from "../lib/api";

interface State {
    hasError: boolean;
    message: string;
    componentStack: string;
}

export class AppErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
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
        console.error("[AdminErrorBoundary] Render failed:", error.message);
        console.error(info.componentStack);
        this.setState({ componentStack: info.componentStack ?? "" });
    }

    softReset = () => {
        this.setState({ hasError: false, message: "", componentStack: "" });
    };

    hardRecover = () => {
        clearToken();
        window.location.href = "/login";
    };

    render() {
        if (this.state.hasError) {
            return (
                <div className="flex min-h-screen items-center justify-center bg-surface px-md">
                    <div className="bg-surface-container-lowest border border-outline-variant rounded p-xl max-w-md w-full text-center">
                        <p className="font-label-caps text-label-caps text-secondary uppercase mb-sm">Admin Console</p>
                        <h2 className="font-display-title text-display-title text-primary mb-sm">Something went wrong</h2>
                        <p className="font-body-sm text-body-sm text-secondary mb-lg">{this.state.message}</p>
                        {import.meta.env.DEV && this.state.componentStack && (
                            <pre className="text-left text-xs text-secondary bg-surface-container rounded p-md mb-lg overflow-auto max-h-40">
                                {this.state.componentStack}
                            </pre>
                        )}
                        <div className="flex gap-sm justify-center">
                            <button
                                className="border border-outline text-on-surface hover:bg-surface-container font-body-sm text-body-sm font-semibold px-lg py-sm rounded transition-colors"
                                onClick={this.softReset}
                                type="button"
                            >
                                Try again
                            </button>
                            <button
                                className="bg-primary-container text-on-primary hover:opacity-90 font-body-sm text-body-sm font-semibold px-lg py-sm rounded transition-opacity"
                                onClick={this.hardRecover}
                                type="button"
                            >
                                Return to login
                            </button>
                        </div>
                    </div>
                </div>
            );
        }
        return this.props.children;
    }
}
