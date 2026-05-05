import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

export default function AdminLayout() {
    return (
        <div className="flex h-full">
            <Sidebar />
            <main className="flex-1 overflow-auto bg-[#0f172a]">
                <div className="max-w-6xl mx-auto px-8 py-8">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
