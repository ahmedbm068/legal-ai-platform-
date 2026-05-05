import { type FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { usePortal } from "../context/PortalContext";
import { PASSWORD_HINT, PASSWORD_POLICY_REGEX } from "../portalPresentation";

type AuthMode = "login" | "register";

export default function PortalAuthPage() {
    const {
        isAuthenticated,
        authBusy,
        authError,
        authMessage,
        loginCodePending,
        login,
        verifyCode,
        register,
        clearAuthMessages,
    } = usePortal();

    const [mode, setMode] = useState<AuthMode>("login");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [loginCode, setLoginCode] = useState("");
    const [tenantSlug, setTenantSlug] = useState("");
    const [fullName, setFullName] = useState("");
    const [phone, setPhone] = useState("");
    const [address, setAddress] = useState("");

    if (isAuthenticated) {
        return <Navigate to="/dashboard" replace />;
    }

    function switchMode(next: AuthMode) {
        setMode(next);
        clearAuthMessages();
        setLoginCode("");
        setPassword("");
        setConfirmPassword("");
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();

        if (mode === "register") {
            if (password !== confirmPassword) {
                return;
            }
            if (!PASSWORD_POLICY_REGEX.test(password)) {
                return;
            }
            const ok = await register({ tenant_slug: tenantSlug.trim(), full_name: fullName, email, password, phone: phone || undefined, address: address || undefined });
            if (ok) switchMode("login");
            return;
        }

        if (loginCodePending) {
            await verifyCode(email, loginCode.trim());
            return;
        }

        await login(email, password);
    }

    return (
        <div className="portal-root">
            <div className="ambient-background" />

            <section className="card auth-card">
                <header>
                    <p className="eyebrow">Secure Client Workspace</p>
                    <h2>{mode === "login" ? "Sign in to your portal" : "Create your portal account"}</h2>
                    <p>
                        {mode === "login"
                            ? "Access your legal matters, documents, and consultation status."
                            : "Register once to get full portal access linked to your firm."}
                    </p>
                </header>

                {authError ? <p className="error-msg">{authError}</p> : null}
                {authMessage ? <p className="success-msg">{authMessage}</p> : null}

                <form onSubmit={(e) => void handleSubmit(e)}>
                    {mode === "register" ? (
                        <>
                            <label>
                                <span>Firm slug</span>
                                <input
                                    required
                                    type="text"
                                    value={tenantSlug}
                                    onChange={(e) => setTenantSlug(e.target.value)}
                                    placeholder="your-firm-slug"
                                    autoComplete="organization"
                                />
                            </label>
                            <label>
                                <span>Full name</span>
                                <input
                                    required
                                    type="text"
                                    value={fullName}
                                    onChange={(e) => setFullName(e.target.value)}
                                    autoComplete="name"
                                />
                            </label>
                        </>
                    ) : null}

                    <label>
                        <span>Email</span>
                        <input
                            required
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            autoComplete="email"
                            disabled={loginCodePending}
                        />
                    </label>

                    {!loginCodePending ? (
                        <label>
                            <span>Password</span>
                            <input
                                required
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                autoComplete={mode === "register" ? "new-password" : "current-password"}
                            />
                        </label>
                    ) : null}

                    {mode === "register" ? (
                        <>
                            {password && !PASSWORD_POLICY_REGEX.test(password) ? (
                                <p className="field-hint">{PASSWORD_HINT}</p>
                            ) : null}
                            <label>
                                <span>Confirm password</span>
                                <input
                                    required
                                    type="password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    autoComplete="new-password"
                                />
                            </label>
                            {confirmPassword && password !== confirmPassword ? (
                                <p className="field-hint error-msg">Passwords do not match.</p>
                            ) : null}
                            <label>
                                <span>Phone (optional)</span>
                                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" />
                            </label>
                            <label>
                                <span>Address (optional)</span>
                                <input type="text" value={address} onChange={(e) => setAddress(e.target.value)} autoComplete="street-address" />
                            </label>
                        </>
                    ) : null}

                    {loginCodePending ? (
                        <label>
                            <span>Verification code</span>
                            <input
                                required
                                type="text"
                                value={loginCode}
                                onChange={(e) => setLoginCode(e.target.value)}
                                placeholder="Enter the code sent to your email"
                                autoComplete="one-time-code"
                            />
                        </label>
                    ) : null}

                    <button className="btn primary" disabled={authBusy} type="submit">
                        {authBusy
                            ? "Please wait…"
                            : mode === "register"
                                ? "Create account"
                                : loginCodePending
                                    ? "Verify code"
                                    : "Sign in"}
                    </button>
                </form>

                <footer className="auth-switch">
                    {mode === "login" ? (
                        <p>
                            No account?{" "}
                            <button className="link-btn" onClick={() => switchMode("register")} type="button">
                                Register
                            </button>
                        </p>
                    ) : (
                        <p>
                            Already registered?{" "}
                            <button className="link-btn" onClick={() => switchMode("login")} type="button">
                                Sign in
                            </button>
                        </p>
                    )}
                    {loginCodePending ? (
                        <p>
                            <button
                                className="link-btn"
                                onClick={() => { clearAuthMessages(); setLoginCode(""); }}
                                type="button"
                            >
                                Back to sign in
                            </button>
                        </p>
                    ) : null}
                </footer>
            </section>
        </div>
    );
}
