import { useMemo, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";

type AuthMode = "login" | "register";

const SINGLE_FIRM_NAME = (import.meta.env.VITE_DEFAULT_TENANT_NAME?.trim() || "Arbi Mostaissier");

export default function AuthPage() {
    const navigate = useNavigate();
    const location = useLocation();
    const {
        authError,
        authMessage,
        authBusy,
        isAuthenticated,
        login,
        register,
        sessionReady,
        t,
    } = useRoutedWorkspace();

    const [mode, setMode] = useState<AuthMode>("login");
    const [name, setName] = useState("");
    const [inviteToken, setInviteToken] = useState("");
    const [role, setRole] = useState<"lawyer" | "assistant" | "admin">("lawyer");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");

    const redirectTarget = useMemo(() => {
        const from = (location.state as { from?: string } | null)?.from;
        return from && from !== "/auth" ? from : "/dashboard";
    }, [location.state]);

    if (sessionReady && isAuthenticated) {
        return <Navigate replace to={redirectTarget} />;
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (mode === "login") {
            const ok = await login(email, password);
            if (ok) {
                navigate(redirectTarget, { replace: true });
            }
            return;
        }

        const created = await register({
            name,
            email,
            password,
            role,
            tenantName: SINGLE_FIRM_NAME,
            inviteToken,
        });
        if (created) {
            setMode("login");
        }
    }

    return (
        <section className="shell-page shell-auth-page">
            <article className="shell-card shell-auth-card">
                <header className="shell-page-header">
                    <p className="shell-page-kicker">{t("authKicker", "Secure Access")}</p>
                    <h2>{mode === "login" ? t("authSignInTitle", "Sign in to your legal workspace") : t("authRegisterTitle", "Create your legal workspace account")}</h2>
                    <p>
                        {mode === "login"
                            ? t("authSignInSubtitle", "Use your existing credentials to open routed workspace pages.")
                            : t("authRegisterSubtitle", "Register once, then sign in to continue.")}
                    </p>
                </header>

                <form className="shell-auth-form" onSubmit={handleSubmit}>
                    {mode === "register" ? (
                        <>
                            <label>
                                <span>{t("fullName", "Full name")}</span>
                                <input onChange={(event) => setName(event.target.value)} required type="text" value={name} />
                            </label>
                            <label>
                                <span>{t("inviteToken", "Invite token")}</span>
                                <input onChange={(event) => setInviteToken(event.target.value)} type="text" value={inviteToken} />
                            </label>
                            <label>
                                <span>{t("role", "Role")}</span>
                                <select onChange={(event) => setRole(event.target.value as "lawyer" | "assistant" | "admin")} value={role}>
                                    <option value="lawyer">{t("roleLawyer", "Lawyer")}</option>
                                    <option value="assistant">{t("roleAssistant", "Assistant")}</option>
                                    <option value="admin">{t("roleAdmin", "Admin")}</option>
                                </select>
                            </label>
                        </>
                    ) : null}

                    <label>
                        <span>{t("email", "Email")}</span>
                        <input
                            autoComplete="email"
                            onChange={(event) => setEmail(event.target.value)}
                            required
                            type="email"
                            value={email}
                        />
                    </label>
                    <label>
                        <span>{t("password", "Password")}</span>
                        <input
                            autoComplete={mode === "login" ? "current-password" : "new-password"}
                            onChange={(event) => setPassword(event.target.value)}
                            required
                            type="password"
                            value={password}
                        />
                    </label>

                    <button disabled={authBusy} type="submit">
                        {authBusy ? t("working", "Working...") : mode === "login" ? t("login", "Login") : t("createAccount", "Create account")}
                    </button>
                </form>

                {authError ? <p className="shell-error-text">{authError}</p> : null}
                {authMessage ? <p className="shell-success-text">{authMessage}</p> : null}

                <div className="shell-auth-switch">
                    {mode === "login" ? (
                        <button onClick={() => setMode("register")} type="button">
                            {t("needAccount", "Need an account? Register")}
                        </button>
                    ) : (
                        <button onClick={() => setMode("login")} type="button">
                            {t("backToLogin", "Already registered? Back to login")}
                        </button>
                    )}
                </div>
            </article>
        </section>
    );
}
