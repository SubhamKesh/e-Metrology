import { PageHeader } from "@/components/layout/AppShell";
import { ApplicationsTable } from "@/components/domain/ApplicationsTable";
import { useApplications } from "@/hooks/useData";
import type { Role } from "@/lib/types";

export function OfficerQueue({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const { data, isLoading, isError, error, refetch } = useApplications({ pollInterval: 5000 });
  return (
    <div>
      <PageHeader title="Verification queue" description="Unassigned applications waiting to be claimed." />
      <ApplicationsTable
        applications={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath={`/app/${role}/applications`}
        emptyDescription="No unassigned applications right now — check back soon."
      />
    </div>
  );
}

export function OfficerAssignments({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const { data, isLoading, isError, error, refetch } = useApplications({ mine: true, pollInterval: 5000 });
  return (
    <div>
      <PageHeader title="My assignments" description="Applications currently assigned to you." />
      <ApplicationsTable
        applications={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath={`/app/${role}/assignments`}
        emptyDescription="Claim an application from the queue to see it here."
      />
    </div>
  );
}
