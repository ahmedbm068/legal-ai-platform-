import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const NAV = [
    { to: "/users", label: "Users", icon: "👤" },
    { to: "/cases", label: "Cases", icon: "📁" },
    { to: "/big-agents", label: "Big Agents", icon: "🧠" },
    { to: "/audit", label: "Audit Log", icon: "📋" },
    { to: "/health", label: "System Health", icon: "📊" },
];

export default function Sidebar() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = () => {
        logout();
        navigate("/login");
    };

    return (
        <aside className="flex flex-col w-56 min-h-full bg-[#0a1628] border-r border-slate-800 shrink-0">
            {/* Logo */}
            <div className="px-5 py-5 border-b border-slate-800">
                <div className="flex items-center gap-2">
                    <span className="text-brand-400 text-xl font-bold leading-none">⚖</span>
                    <div>
                        <p className="text-white text-sm font-semibold leading-tight">Legal AI</p>
                        <p className="text-slate-500 text-xs">Admin Console</p>
                    </div>
                </div>
            </div>

            {/* Nav */}
            <nav className="flex-1 py-4 px-2">
                {NAV.map((item) => (
                    <NavLink
                        key={item.to}
                        to={item.to}
                        className={({ isActive }) =>
                            `flex items-center gap-3 px-3 py-2 mb-1 rounded-lg text-sm transition-colors ${isActive
                                ? "bg-brand-600/20 text-brand-400 font-medium"
                                : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                            }`
                        }
                    >
                        <span>{item.icon}</span>
                        {item.label}
                    </NavLink>
                ))}
            </nav>

            {/* Footer */}
            <div className="px-4 py-4 border-t border-slate-800">
                <p className="text-slate-500 text-xs mb-1 truncate">{user?.email}</p>
                <button
                    onClick={handleLogout}
                    className="text-xs text-slate-400 hover:text-red-400 transition-colors"
                >
                    Sign out
                </button>
            </div>
        </aside>
    );
}
