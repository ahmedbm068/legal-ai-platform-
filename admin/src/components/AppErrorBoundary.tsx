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
                <div className="flex h-screen items-center justify-center bg-[#0f172a]">
                    <div className="bg-[#1e293b] rounded-xl p-8 max-w-md w-full text-center shadow-lg">
                        <p className="text-slate-400 text-xs uppercase tracking-widest mb-2">Admin Console</p>
                        <h2 className="text-white text-xl font-semibold mb-2">Something went wrong</h2>
                        <p className="text-slate-400 text-sm mb-6">{this.state.message}</p>
                        {import.meta.env.DEV && this.state.componentStack && (
                            <pre className="text-left text-xs text-slate-500 bg-slate-900 rounded-lg p-3 mb-6 overflow-auto max-h-40">
                                {this.state.componentStack}
                            </pre>
                        )}
                        <div className="flex gap-3 justify-center">
                            <button
                                className="border border-slate-600 text-slate-300 hover:border-slate-400 text-sm font-medium px-5 py-2 rounded-lg"
                                onClick={this.softReset}
                                type="button"
                            >
                                Try again
                            </button>
                            <button
                                className="bg-brand-500 hover:bg-brand-400 text-white text-sm font-medium px-6 py-2 rounded-lg"
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
