import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { apiSystemHealth, type SystemHealth } from "../lib/api";
import { PageHeader } from "../components/ui";

type Section = "general" | "security" | "tenant" | "notifications";

const SUB_NAV: { id: Section; label: string; icon: string }[] = [
    { id: "general", label: "General", icon: "tune" },
    { id: "security", label: "Security", icon: "shield" },
    { id: "tenant", label: "Tenant Policies", icon: "policy" },
    { id: "notifications", label: "Notifications", icon: "notifications" },
];

function monogram(name: string): string {
    const p = name.trim().split(/\s+/);
    return (p.length === 1 ? p[0].slice(0, 2) : p[0][0] + p[p.length - 1][0]).toUpperCase();
}

function Placeholder({ title }: { title: string }) {
    return (
        <section className="bg-surface-container-lowest border border-outline-variant rounded p-lg">
            <div className="flex flex-col items-center justify-center text-center py-xl">
                <div className="w-16 h-16 rounded-full bg-surface-container-high border border-outline-variant flex items-center justify-center mb-md">
                    <span className="material-symbols-outlined text-[28px] text-secondary">
                        construction
                    </span>
                </div>
                <h3 className="font-section-header text-section-header text-on-surface mb-xs">
                    {title} settings are not yet available
                </h3>
                <p className="font-body-sm text-body-sm text-secondary max-w-md">
                    There is no backend for {title.toLowerCase()} configuration yet. This
                    section will be enabled once the corresponding API exists.
                </p>
                <span className="mt-md font-label-caps text-label-caps text-secondary uppercase bg-surface-container px-md py-xs rounded">
                    Backend pending
                </span>
            </div>
        </section>
    );
}

export default function SettingsPage() {
    const { user, logout } = useAuth();
    const { addToast } = useToast();
    const navigate = useNavigate();
    const [section, setSection] = useState<Section>("general");
    const [health, setHealth] = useState<SystemHealth | null>(null);
    const [healthErr, setHealthErr] = useState(false);

    useEffect(() => {
        apiSystemHealth()
            .then(setHealth)
            .catch(() => setHealthErr(true));
    }, []);

    const handleLogout = () => {
        logout();
        navigate("/login");
    };

    const notAvailable = (what: string) =>
        addToast(`${what} is not available yet — backend pending.`, "info");

    return (
        <div>
            <PageHeader
                title="Platform Settings"
                subtitle="Manage global configurations, security protocols, and administrative profiles."
            />

            <div className="flex flex-col lg:flex-row gap-lg">
                {/* Vertical sub-nav */}
                <nav className="lg:w-60 flex flex-col gap-xs lg:sticky lg:top-lg h-fit shrink-0">
                    {SUB_NAV.map((s) => {
                        const active = section === s.id;
                        return (
                            <button
                                key={s.id}
                                onClick={() => setSection(s.id)}
                                className={`flex items-center gap-sm px-md py-sm rounded font-body-md text-body-md transition-colors text-left ${active
                                    ? "bg-surface-container-lowest border border-outline-variant text-primary font-bold"
                                    : "text-secondary hover:bg-surface-container border border-transparent"
                                    }`}
                            >
                                <span className="material-symbols-outlined text-[20px]">
                                    {s.icon}
                                </span>
                                {s.label}
                            </button>
                        );
                    })}
                </nav>

                {/* Content */}
                <div className="flex-1 space-y-lg min-w-0">
                    {section !== "general" ? (
                        <Placeholder
                            title={SUB_NAV.find((s) => s.id === section)!.label}
                        />
                    ) : (
                        <>
                            {/* Global Configuration — UI present, backend pending */}
                            <section className="bg-surface-container-lowest border border-outline-variant rounded p-lg">
                                <h3 className="font-section-header text-section-header text-primary mb-lg pb-md border-b border-outline-variant">
                                    Global Configuration
                                </h3>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-xl">
                                    <div className="space-y-sm">
                                        <label className="font-label-caps text-label-caps text-secondary uppercase block">
                                            Platform Name
                                        </label>
                                        <input
                                            defaultValue="Lexington Admin Console"
                                            disabled
                                            className="w-full border border-outline-variant rounded px-sm py-sm font-body-md text-body-md bg-surface-container text-secondary cursor-not-allowed"
                                        />
                                    </div>
                                    <div className="space-y-sm">
                                        <label className="font-label-caps text-label-caps text-secondary uppercase block">
                                            Environment Status
                                        </label>
                                        <div className="flex items-center gap-md pt-xs">
                                            <span className="font-body-md text-body-md text-primary font-bold">
                                                Production
                                            </span>
                                            <span
                                                aria-disabled
                                                className="relative inline-flex h-6 w-11 flex-shrink-0 rounded-full bg-primary-container opacity-60 cursor-not-allowed"
                                            >
                                                <span className="translate-x-5 inline-block h-5 w-5 transform rounded-full bg-white shadow transition" />
                                            </span>
                                            <span className="font-body-md text-body-md text-secondary">
                                                Staging
                                            </span>
                                        </div>
                                    </div>
                                    <div className="space-y-sm md:col-span-2 max-w-md">
                                        <label className="font-label-caps text-label-caps text-secondary uppercase block">
                                            Default Tenant Policy
                                        </label>
                                        <select
                                            disabled
                                            className="w-full border border-outline-variant rounded px-sm py-sm font-body-md text-body-md bg-surface-container text-secondary cursor-not-allowed"
                                        >
                                            <option>Strict — Full Verification Required</option>
                                        </select>
                                        <p className="text-[11px] text-secondary italic">
                                            Platform configuration has no backend yet — these
                                            controls are read-only.
                                        </p>
                                    </div>
                                </div>
                                <div className="mt-xl pt-lg border-t border-outline-variant flex justify-end">
                                    <button
                                        onClick={() => notAvailable("Saving platform configuration")}
                                        className="bg-primary-container text-on-primary px-lg py-sm font-section-header text-[14px] rounded hover:bg-surface-tint transition-colors"
                                    >
                                        Save Changes
                                    </button>
                                </div>
                            </section>

                            {/* Administrative Profile — REAL data */}
                            <section className="bg-surface-container-lowest border border-outline-variant rounded p-lg">
                                <h3 className="font-section-header text-section-header text-primary mb-lg pb-md border-b border-outline-variant">
                                    Your Administrative Profile
                                </h3>
                                <div className="flex flex-col sm:flex-row items-start gap-xl">
                                    <div className="w-20 h-20 rounded bg-surface-container-high border border-outline-variant flex items-center justify-center text-[22px] font-bold text-secondary shrink-0">
                                        {user ? monogram(user.name) : "—"}
                                    </div>
                                    <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-lg w-full">
                                        <div className="space-y-sm">
                                            <label className="font-label-caps text-label-caps text-secondary uppercase block">
                                                Full Name
                                            </label>
                                            <p className="font-body-md text-body-md text-primary py-sm border-b border-outline-variant">
                                                {user?.name ?? "—"}
                                            </p>
                                        </div>
                                        <div className="space-y-sm">
                                            <label className="font-label-caps text-label-caps text-secondary uppercase block">
                                                Email Address
                                            </label>
                                            <p className="font-body-md text-body-md text-primary py-sm border-b border-outline-variant break-all">
                                                {user?.email ?? "—"}
                                            </p>
                                        </div>
                                        <div className="space-y-sm">
                                            <label className="font-label-caps text-label-caps text-secondary uppercase block">
                                                Role
                                            </label>
                                            <div className="py-xs">
                                                <span className="px-sm py-[2px] bg-primary-fixed-dim text-on-primary-fixed font-label-caps text-label-caps uppercase rounded">
                                                    {user?.role ?? "—"}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="space-y-sm">
                                            <label className="font-label-caps text-label-caps text-secondary uppercase block">
                                                Tenant
                                            </label>
                                            <p className="font-body-md text-body-md text-primary py-sm border-b border-outline-variant">
                                                {user ? `#${user.tenant_id}` : "—"}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-lg pt-lg border-t border-outline-variant flex items-center justify-between gap-md flex-wrap">
                                    <button
                                        onClick={() => notAvailable("Changing password")}
                                        className="flex items-center gap-sm text-secondary hover:text-primary transition-colors font-body-sm text-body-sm font-bold"
                                    >
                                        <span className="material-symbols-outlined text-[18px]">
                                            lock_reset
                                        </span>
                                        Change Password
                                    </button>
                                    <button
                                        onClick={handleLogout}
                                        className="flex items-center gap-sm bg-primary-container text-on-primary px-md py-sm rounded font-body-sm text-body-sm font-semibold hover:bg-surface-tint transition-colors"
                                    >
                                        <span className="material-symbols-outlined text-[18px]">
                                            logout
                                        </span>
                                        Sign out
                                    </button>
                                </div>
                            </section>

                            {/* Critical Actions + System Health */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-lg">
                                <div className="md:col-span-2 bg-surface-container-low border border-outline-variant rounded p-lg">
                                    <div className="flex items-center gap-md mb-md">
                                        <span className="material-symbols-outlined text-error">
                                            warning
                                        </span>
                                        <h4 className="font-section-header text-section-header text-error">
                                            Critical Actions
                                        </h4>
                                    </div>
                                    <p className="font-body-sm text-body-sm text-secondary mb-lg">
                                        Actions taken here are permanent and affect all
                                        tenants. These controls have no backend yet and are
                                        intentionally inert.
                                    </p>
                                    <div className="flex gap-md flex-wrap">
                                        <button
                                            onClick={() => notAvailable("Maintenance mode")}
                                            className="border border-outline px-md py-sm font-body-sm text-body-sm font-bold rounded hover:bg-surface-container-lowest transition-colors"
                                        >
                                            Maintenance Mode
                                        </button>
                                        <button
                                            onClick={() => notAvailable("Purging audit logs")}
                                            className="border border-error text-error px-md py-sm font-body-sm text-body-sm font-bold rounded hover:bg-error hover:text-on-error transition-colors"
                                        >
                                            Purge Audit Logs
                                        </button>
                                    </div>
                                </div>

                                <div className="bg-primary-container text-on-primary rounded p-lg flex flex-col justify-between gap-lg">
                                    <h4 className="font-label-caps text-label-caps text-on-primary-container uppercase">
                                        System Health
                                    </h4>
                                    {healthErr ? (
                                        <div>
                                            <p className="font-section-header text-section-header">
                                                Unavailable
                                            </p>
                                            <p className="font-body-sm text-body-sm opacity-80">
                                                Health endpoint not reachable
                                            </p>
                                        </div>
                                    ) : (
                                        <div className="space-y-sm">
                                            <div className="grid grid-cols-2 gap-sm">
                                                <Stat
                                                    label="Users"
                                                    value={health?.total_users}
                                                />
                                                <Stat
                                                    label="Cases"
                                                    value={health?.total_cases}
                                                />
                                                <Stat
                                                    label="Documents"
                                                    value={health?.total_documents}
                                                />
                                                <Stat
                                                    label="Audit"
                                                    value={health?.total_audit_entries}
                                                />
                                            </div>
                                            <p className="font-body-sm text-body-sm opacity-80 pt-sm">
                                                Live platform counters
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

function Stat({ label, value }: { label: string; value?: number }) {
    return (
        <div>
            <p className="font-page-header text-[22px] leading-tight">
                {value != null ? value.toLocaleString() : "—"}
            </p>
            <p className="font-label-caps text-label-caps uppercase opacity-70">
                {label}
            </p>
        </div>
    );
}
