import { Link } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";

export default function DashboardPage() {
    const { t } = useRoutedWorkspace();

    const upcomingDeadlines = [
        {
            id: 1,
            label: t("dashboardDeadline1Label", "Response to opposing counsel"),
            due: t("dashboardDeadline1Due", "Today, 16:00"),
            reason: t("dashboardDeadline1Reason", "Court procedure deadline tied to active dispute milestone."),
        },
        {
            id: 2,
            label: t("dashboardDeadline2Label", "Client evidence completion"),
            due: t("dashboardDeadline2Due", "Tomorrow, 10:00"),
            reason: t("dashboardDeadline2Reason", "Missing invoices block damages quantification."),
        },
        {
            id: 3,
            label: t("dashboardDeadline3Label", "Settlement strategy review"),
            due: t("dashboardDeadline3Due", "Apr 21, 09:30"),
            reason: t("dashboardDeadline3Reason", "Negotiation posture must be finalized before outreach."),
        },
    ];

    const urgentRisks = [
        t("dashboardRisk1", "Unanswered notice period in supplier agreement amendment."),
        t("dashboardRisk2", "Payment timeline contradiction between annex and email record."),
        t("dashboardRisk3", "Evidence chain gap for one voice recording transcript."),
    ];

    const localizedActions = [
        { label: t("actionOpenCaseWorkspace", "Open case workspace"), to: "/cases" },
        { label: t("actionAskAssistant", "Ask contextual assistant"), to: "/assistant" },
        { label: t("actionReviewQueue", "Review upload queue"), to: "/documents" },
    ];

    return (
        <section className="shell-page">
            <header className="shell-page-header">
                <p className="shell-page-kicker">{t("dashboardKicker", "Home Dashboard")}</p>
                <h2>{t("dashboardTitle", "Today priorities")}</h2>
                <p>{t("dashboardSubtitle", "Shows only deadlines, urgent legal risks, and 3 primary actions.")}</p>
            </header>

            <div className="shell-grid shell-grid-2">
                <article className="shell-card">
                    <h3>{t("upcomingDeadlines", "Upcoming deadlines")}</h3>
                    <ul className="shell-list">
                        {upcomingDeadlines.map((item) => (
                            <li key={item.id}>
                                <strong>{item.label}</strong>
                                <span>{item.due}</span>
                                <p>{item.reason}</p>
                            </li>
                        ))}
                    </ul>
                </article>

                <article className="shell-card">
                    <h3>{t("urgentRisks", "Urgent risks")}</h3>
                    <ul className="shell-list shell-tight-list">
                        {urgentRisks.map((risk) => (
                            <li key={risk}>{risk}</li>
                        ))}
                    </ul>
                </article>
            </div>

            <article className="shell-card">
                <h3>{t("primaryActions", "Primary actions")}</h3>
                <div className="shell-action-row">
                    {localizedActions.map((action) => (
                        <Link className="shell-action-link" key={action.to} to={action.to}>
                            {action.label}
                        </Link>
                    ))}
                </div>
            </article>
        </section>
    );
}
