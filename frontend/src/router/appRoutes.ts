export type AppRoute = {
    path: string;
    label: string;
    description: string;
    useSelectedCase?: boolean;
};

export const APP_ROUTES: AppRoute[] = [
    {
        path: "/dashboard",
        label: "Home Dashboard",
        description: "Today priorities, urgent risks, and key actions",
    },
    {
        path: "/cases",
        label: "Cases",
        description: "Case list and tabbed detail workflow",
        useSelectedCase: true,
    },
    {
        path: "/assistant",
        label: "Assistant",
        description: "Case-contextual legal copilot",
        useSelectedCase: true,
    },
    {
        path: "/documents",
        label: "Documents",
        description: "Upload and processing queue",
        useSelectedCase: true,
    },
    {
        path: "/editor",
        label: "Legal Editor",
        description: "Draft, verify, version, and export",
        useSelectedCase: true,
    },
    {
        path: "/calendar",
        label: "Calendar",
        description: "Deadlines and why-they-matter",
        useSelectedCase: true,
    },
    {
        path: "/settings",
        label: "Settings / Profile",
        description: "Admin and workspace preferences",
    },
];
