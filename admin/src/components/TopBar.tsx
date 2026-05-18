import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function TopBar() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = () => {
        logout();
        navigate("/login");
    };

    return (
        <header className="bg-surface text-primary font-body-sm fixed top-0 right-0 left-sidebar-width h-topbar-height border-b border-outline-variant flex justify-between items-center px-lg z-40">
            <h1 className="font-display-title text-display-title text-primary">
                Lexington Admin Console
            </h1>

            <div className="flex items-center gap-md">
                <span className="flex items-center px-sm h-full text-primary border-b-2 border-primary">
                    Production
                </span>

                <div className="flex items-center gap-sm border-l border-outline-variant pl-md ml-sm">
                    <button
                        type="button"
                        className="p-sm text-secondary hover:text-primary transition-colors rounded-full hover:bg-surface-container"
                        aria-label="Notifications"
                    >
                        <span className="material-symbols-outlined">notifications</span>
                    </button>
                    <div className="group relative">
                        <button
                            type="button"
                            className="p-sm text-secondary hover:text-primary transition-colors rounded-full hover:bg-surface-container"
                            aria-label="Account"
                        >
                            <span className="material-symbols-outlined">account_circle</span>
                        </button>
                        <div className="absolute right-0 top-full mt-xs w-56 bg-surface-container-lowest border border-outline-variant rounded shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all">
                            <div className="px-md py-sm border-b border-outline-variant">
                                <p className="font-body-md text-body-md text-on-surface font-semibold truncate">
                                    {user?.name ?? "Admin"}
                                </p>
                                <p className="font-body-sm text-body-sm text-secondary truncate">
                                    {user?.email}
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={handleLogout}
                                className="w-full text-left px-md py-sm font-body-sm text-body-sm text-secondary hover:bg-surface-container hover:text-error transition-colors"
                            >
                                Sign out
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </header>
    );
}
