import { NavLink } from "react-router-dom";

const NAV = [
    { to: "/overview", label: "Overview", icon: "dashboard" },
    { to: "/users", label: "Users & Staff", icon: "group" },
    { to: "/clients", label: "Clients", icon: "person_book" },
    { to: "/cases", label: "Cases", icon: "folder_shared" },
    { to: "/billing", label: "Billing & Invoices", icon: "payments" },
    { to: "/jobs", label: "Background Jobs", icon: "settings_backup_restore" },
    { to: "/audit", label: "Audit Log", icon: "history" },
];

const linkClass = (isActive: boolean) =>
    [
        "flex items-center gap-md px-sm py-sm rounded transition-colors cursor-pointer active:opacity-80",
        isActive
            ? "text-primary font-bold bg-secondary-container"
            : "text-secondary hover:bg-surface-container",
    ].join(" ");

export default function Sidebar() {
    return (
        <nav className="bg-surface text-primary font-body-md fixed left-0 top-0 h-full w-sidebar-width border-r border-outline-variant flex flex-col overflow-y-auto px-md py-lg z-50">
            <div className="mb-xl px-sm flex items-center gap-sm">
                <div className="w-8 h-8 bg-surface-container-high rounded-full flex items-center justify-center border border-outline-variant">
                    <span className="material-symbols-outlined text-[16px] text-primary">domain</span>
                </div>
                <div>
                    <div className="font-page-header text-page-header text-primary leading-none">
                        Lexington
                    </div>
                    <div className="font-label-caps text-label-caps text-secondary uppercase mt-xs">
                        Practice Admin
                    </div>
                </div>
            </div>

            <ul className="flex flex-col gap-xs flex-grow">
                {NAV.map((item) => (
                    <li key={item.to}>
                        <NavLink to={item.to} className={({ isActive }) => linkClass(isActive)}>
                            <span className="material-symbols-outlined">{item.icon}</span>
                            <span>{item.label}</span>
                        </NavLink>
                    </li>
                ))}
            </ul>

            <div className="mt-auto pt-md border-t border-outline-variant">
                <NavLink
                    to="/settings"
                    className={({ isActive }) => linkClass(isActive)}
                >
                    <span className="material-symbols-outlined">settings</span>
                    <span>Settings</span>
                </NavLink>
            </div>
        </nav>
    );
}
