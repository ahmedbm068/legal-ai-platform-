import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

export default function AdminLayout() {
    return (
        <div className="min-h-screen bg-surface text-on-surface font-body-md">
            <Sidebar />
            <TopBar />
            <main className="ml-sidebar-width mt-topbar-height p-lg max-w-[1440px] mx-auto">
                <Outlet />
            </main>
        </div>
    );
}
