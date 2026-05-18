import { PageHeader } from "../components/ui";
import ComingSoon from "../components/ComingSoon";

export default function JobsPage() {
    return (
        <div>
            <PageHeader
                title="Background Jobs"
                subtitle="Scheduled syncs, document processing queues, and job health."
            />
            <ComingSoon
                icon="settings_backup_restore"
                title="Job monitoring is not yet wired"
                description="There is no job-queue endpoint on the backend yet. Once a jobs API is available, this page will show running, queued, and failed jobs with retry controls."
            />
        </div>
    );
}
