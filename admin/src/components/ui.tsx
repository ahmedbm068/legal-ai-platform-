import type { ReactNode } from "react";

export function PageHeader({
    title,
    subtitle,
    actions,
}: {
    title: string;
    subtitle?: string;
    actions?: ReactNode;
}) {
    return (
        <header className="mb-lg flex justify-between items-end gap-md">
            <div>
                <h2 className="font-page-header text-page-header text-on-surface">{title}</h2>
                {subtitle && (
                    <p className="font-body-sm text-body-sm text-secondary mt-xs">{subtitle}</p>
                )}
            </div>
            {actions && <div className="flex gap-sm shrink-0">{actions}</div>}
        </header>
    );
}

export function Panel({
    title,
    icon,
    actions,
    children,
    className = "",
}: {
    title?: string;
    icon?: ReactNode;
    actions?: ReactNode;
    children: ReactNode;
    className?: string;
}) {
    return (
        <section
            className={`bg-surface-container-lowest border border-outline-variant rounded flex flex-col ${className}`}
        >
            {title && (
                <div className="p-md border-b border-outline-variant flex justify-between items-center bg-surface-bright">
                    <h3 className="font-section-header text-section-header text-on-surface flex items-center gap-xs">
                        {icon}
                        {title}
                    </h3>
                    {actions}
                </div>
            )}
            {children}
        </section>
    );
}

export function Button({
    children,
    icon,
    variant = "outline",
    ...props
}: {
    children: ReactNode;
    icon?: string;
    variant?: "outline" | "primary";
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
    const base =
        "px-md py-sm rounded font-body-sm text-body-sm flex items-center gap-sm transition-colors disabled:opacity-50";
    const styles =
        variant === "primary"
            ? "bg-primary-container text-on-primary hover:opacity-90"
            : "bg-surface border border-outline text-on-surface hover:bg-surface-container";
    return (
        <button className={`${base} ${styles}`} {...props}>
            {icon && <span className="material-symbols-outlined text-[16px]">{icon}</span>}
            {children}
        </button>
    );
}

export function SearchInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
    return (
        <div className="relative">
            <span className="material-symbols-outlined absolute left-sm top-1/2 -translate-y-1/2 text-[18px] text-secondary pointer-events-none">
                search
            </span>
            <input
                {...props}
                className="bg-surface-container-lowest border border-outline-variant rounded pl-8 pr-md py-sm font-body-sm text-body-sm text-on-surface placeholder:text-secondary focus:outline-none focus:ring-2 focus:ring-primary-container/30 focus:border-primary-container w-64"
            />
        </div>
    );
}

export function StateMsg({
    kind = "loading",
    children,
}: {
    kind?: "loading" | "error" | "empty";
    children: ReactNode;
}) {
    if (kind === "error") {
        return (
            <p className="font-body-sm text-body-sm text-on-error-container bg-err-bg border border-error-container rounded px-md py-sm">
                {children}
            </p>
        );
    }
    return (
        <p className="font-body-sm text-body-sm text-secondary py-sm">{children}</p>
    );
}
