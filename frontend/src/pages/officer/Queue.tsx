import { PageHeader } from "@/components/layout/AppShell";
import { ApplicationsTable } from "@/components/domain/ApplicationsTable";
import { ApplicationsFilterBar, EMPTY_APPLICATION_FILTERS } from "@/components/domain/ApplicationsFilterBar";
import { useApplications } from "@/hooks/useData";
import { useFilters } from "@/hooks/useFilters";
import { useDrafts } from "@/hooks/useDrafts";
import { useAuth } from "@/context/AuthContext";
import type { Role } from "@/lib/types";

export function OfficerQueue({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const filters = useFilters(EMPTY_APPLICATION_FILTERS);
  const { data, isLoading, isError, error, refetch } = useApplications({ ...filters.query, pollInterval: 5000 });
  return (
    <div>
      <PageHeader title="Verification queue" description="Unassigned applications waiting to be claimed." />
      <ApplicationsFilterBar filters={filters} showStatus={false} />
      <ApplicationsTable
        applications={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath={`/app/${role}/applications`}
        emptyTitle={filters.active ? "No applications match" : undefined}
        emptyDescription={filters.active ? "Try a different search or clear the filters." : "No unassigned applications right now — check back soon."}
      />
    </div>
  );
}

export function OfficerAssignments({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const filters = useFilters(EMPTY_APPLICATION_FILTERS);
  const { data, isLoading, isError, error, refetch } = useApplications({ ...filters.query, mine: true, pollInterval: 5000 });
  const { user } = useAuth();
  const draftIds = new Set(useDrafts(user?.id).map((d) => d.application_id));
  return (
    <div>
      <PageHeader title="My assignments" description="Applications currently assigned to you." />
      <ApplicationsFilterBar filters={filters} exportExtra={{ mine: true }} />
      <ApplicationsTable
        applications={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath={`/app/${role}/assignments`}
        draftIds={draftIds}
        emptyTitle={filters.active ? "No applications match" : undefined}
        emptyDescription={filters.active ? "Try a different search or clear the filters." : "Claim an application from the queue to see it here."}
      />
    </div>
  );
}
