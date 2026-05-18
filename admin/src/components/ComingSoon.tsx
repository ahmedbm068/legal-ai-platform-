import { Panel } from "./ui";

export default function ComingSoon({
    icon,
    title,
    description,
}: {
    icon: string;
    title: string;
    description: string;
}) {
    return (
        <Panel className="h-[420px]">
            <div className="flex flex-col items-center justify-center h-full text-center px-xl">
                <div className="w-16 h-16 rounded-full bg-surface-container-high border border-outline-variant flex items-center justify-center mb-md">
                    <span className="material-symbols-outlined text-[28px] text-secondary">
                        {icon}
                    </span>
                </div>
                <h3 className="font-section-header text-section-header text-on-surface mb-xs">
                    {title}
                </h3>
                <p className="font-body-sm text-body-sm text-secondary max-w-md">
                    {description}
                </p>
                <span className="mt-md font-label-caps text-label-caps text-secondary uppercase bg-surface-container px-md py-xs rounded">
                    Backend pending
                </span>
            </div>
        </Panel>
    );
}
