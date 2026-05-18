import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { usePortal } from "../context/PortalContext";

const NAV_LINKS: Array<{ to: string; label: string }> = [
    { to: "/dashboard", label: "Home" },
    { to: "/cases", label: "My Case" },
    { to: "/documents", label: "Documents" },
    { to: "/messages", label: "Messages" },
    { to: "/appointments", label: "Appointments" },
    { to: "/billing", label: "Billing" },
];

export default function LexingtonShell() {
    const { logout, unreadMessages } = usePortal();
    const navigate = useNavigate();

    return (
        <div className="lexington-scope min-h-screen text-on-surface">
            {/* Top Navigation Shell */}
            <header className="w-full top-0 sticky bg-surface border-b border-outline-variant z-50">
                <div className="max-w-container-max mx-auto flex justify-between items-center h-20 px-gutter">
                    <button
                        type="button"
                        onClick={() => navigate("/dashboard")}
                        className="text-headline-md font-headline-md text-primary tracking-tight bg-transparent border-0 cursor-pointer p-0"
                    >
                        Lexington Portal
                    </button>
                    <nav className="hidden md:flex items-center gap-x-8 h-full">
                        {NAV_LINKS.map((link) => (
                            <NavLink
                                key={link.to}
                                to={link.to}
                                className={({ isActive }) =>
                                    isActive
                                        ? "relative text-primary font-bold border-b-2 border-primary pb-2 font-label-md text-label-md"
                                        : "relative text-on-surface-variant opacity-70 pb-2 font-label-md text-label-md hover:text-primary transition-colors duration-200"
                                }
                            >
                                {link.label}
                                {link.to === "/messages" && unreadMessages > 0 ? (
                                    <span className="absolute -top-2 -right-3 min-w-[18px] h-[18px] px-1 flex items-center justify-center bg-error text-on-error text-[10px] font-bold rounded-full">
                                        {unreadMessages > 9 ? "9+" : unreadMessages}
                                    </span>
                                ) : null}
                            </NavLink>
                        ))}
                    </nav>
                    <div className="flex items-center gap-x-4">
                        <button
                            className="relative p-2 transition-opacity active:opacity-80"
                            type="button"
                            onClick={() => navigate("/messages")}
                            title={unreadMessages > 0 ? `${unreadMessages} unread message(s)` : "Notifications"}
                        >
                            <span className="material-symbols-outlined text-on-surface-variant">notifications</span>
                            {unreadMessages > 0 ? (
                                <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-error rounded-full border border-surface" />
                            ) : null}
                        </button>
                        <button
                            className="p-2 transition-opacity active:opacity-80"
                            type="button"
                            onClick={logout}
                            title="Sign out"
                        >
                            <span className="material-symbols-outlined text-on-surface-variant">account_circle</span>
                        </button>
                    </div>
                </div>
            </header>

            <Outlet />

            {/* Footer Shell */}
            <footer className="w-full py-12 bg-surface border-t border-outline-variant mt-stack-lg">
                <div className="max-w-container-max mx-auto flex flex-col md:flex-row justify-between items-center px-gutter gap-y-6">
                    <div className="font-headline-md text-primary">Lexington Portal</div>
                    <div className="flex gap-x-8">
                        <a className="font-label-md text-label-md text-on-surface-variant hover:text-primary transition-colors" href="#">Privacy Policy</a>
                        <a className="font-label-md text-label-md text-on-surface-variant hover:text-primary transition-colors" href="#">Terms of Service</a>
                        <a className="font-label-md text-label-md text-on-surface-variant hover:text-primary transition-colors" href="#">Help Center</a>
                    </div>
                    <p className="font-label-md text-label-md text-on-surface-variant opacity-70">© 2024 Lexington Legal Tech. All rights reserved.</p>
                </div>
            </footer>
        </div>
    );
}
