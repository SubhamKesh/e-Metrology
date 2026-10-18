import { PageHeader } from "@/components/layout/AppShell";
import { ApplicationsTable } from "@/components/domain/ApplicationsTable";
import { ApplicationsFilterBar, EMPTY_APPLICATION_FILTERS } from "@/components/domain/ApplicationsFilterBar";
import { useApplications } from "@/hooks/useData";
import { useFilters } from "@/hooks/useFilters";

export default function AdminApplications() {
  const filters = useFilters(EMPTY_APPLICATION_FILTERS);
  const { data, isLoading, isError, error, refetch } = useApplications(filters.query);

  return (
    <div>
      <PageHeader title="All applications" description="Every verification application across the system. Search, filter and export what you see." />
      <ApplicationsFilterBar filters={filters} />
      <ApplicationsTable
        applications={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath="/app/admin/applications"
        emptyTitle={filters.active ? "No applications match" : undefined}
        emptyDescription={filters.active ? "Try a different search or clear the filters." : undefined}
      />
    </div>
  );
}
