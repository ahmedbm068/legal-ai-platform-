import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { apiLogin } from "../lib/api";

export default function LoginPage() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPw, setShowPw] = useState(false);
    const [remember, setRemember] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            const res = await apiLogin(email, password);
            await login(res.access_token);
            navigate("/overview");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Login failed");
        } finally {
            setLoading(false);
        }
    };

    const inputCls =
        "w-full bg-surface-container-lowest border border-outline-variant rounded p-sm font-body-md text-body-md text-on-surface placeholder:text-outline focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 focus:outline-none transition-all";

    return (
        <div className="bg-background text-on-surface antialiased min-h-screen flex flex-col justify-center items-center p-md">
            <main className="w-full max-w-[400px] bg-surface-container-lowest border border-outline-variant rounded p-xl flex flex-col gap-xl shadow-[0_1px_2px_rgba(27,28,25,0.04),0_12px_32px_-12px_rgba(0,27,61,0.18)]">
                <header className="text-center flex flex-col gap-xs">
                    <h1 className="font-display-title text-display-title text-primary tracking-tight">
                        Lexington Admin
                    </h1>
                    <p className="font-body-sm text-body-sm text-secondary">
                        Authorized personnel only
                    </p>
                </header>

                <form onSubmit={handleSubmit} className="flex flex-col gap-md" noValidate>
                    <div className="flex flex-col gap-xs">
                        <label
                            className="font-body-sm text-body-sm text-on-surface"
                            htmlFor="email"
                        >
                            Email Address
                        </label>
                        <input
                            id="email"
                            name="email"
                            type="email"
                            autoComplete="email"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className={inputCls}
                            placeholder="admin@lexington.com"
                        />
                    </div>

                    <div className="flex flex-col gap-xs">
                        <label
                            className="font-body-sm text-body-sm text-on-surface"
                            htmlFor="password"
                        >
                            Password
                        </label>
                        <div className="relative">
                            <input
                                id="password"
                                name="password"
                                type={showPw ? "text" : "password"}
                                autoComplete="current-password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className={`${inputCls} pr-10`}
                                placeholder="••••••••"
                            />
                            <button
                                type="button"
                                onClick={() => setShowPw((v) => !v)}
                                tabIndex={-1}
                                aria-label={showPw ? "Hide password" : "Show password"}
                                className="absolute right-sm top-1/2 -translate-y-1/2 text-secondary hover:text-on-surface transition-colors"
                            >
                                <span className="material-symbols-outlined text-[18px]">
                                    {showPw ? "visibility_off" : "visibility"}
                                </span>
                            </button>
                        </div>
                    </div>

                    <div className="flex justify-between items-center py-xs">
                        <label className="flex items-center gap-xs cursor-pointer group">
                            <input
                                type="checkbox"
                                checked={remember}
                                onChange={(e) => setRemember(e.target.checked)}
                                className="rounded-[2px] border-outline-variant text-primary-container focus:ring-0 focus:ring-offset-0 bg-surface-container-lowest w-4 h-4 cursor-pointer"
                            />
                            <span className="font-body-sm text-body-sm text-secondary group-hover:text-on-surface transition-colors">
                                Remember me
                            </span>
                        </label>
                        <a
                            className="font-body-sm text-body-sm text-secondary hover:text-primary-container transition-colors"
                            href="#"
                        >
                            Recover Access
                        </a>
                    </div>

                    {error && (
                        <p
                            role="alert"
                            className="font-body-sm text-body-sm text-on-error-container bg-err-bg border border-error-container rounded px-md py-sm"
                        >
                            {error}
                        </p>
                    )}

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-primary-container text-on-primary font-section-header text-section-header p-sm rounded flex justify-center items-center gap-sm hover:bg-surface-tint disabled:opacity-60 disabled:hover:bg-primary-container transition-colors mt-sm"
                    >
                        {loading && (
                            <span className="material-symbols-outlined text-[18px] animate-spin">
                                progress_activity
                            </span>
                        )}
                        {loading ? "Signing in…" : "Sign In"}
                    </button>
                </form>

                <footer className="text-center pt-md border-t border-outline-variant mt-sm">
                    <p className="font-table-data text-table-data text-secondary">
                        Lexington Practice Management System ©{" "}
                        {new Date().getFullYear()}
                    </p>
                </footer>
            </main>
        </div>
    );
}
