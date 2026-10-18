import { PageHeader } from "@/components/layout/AppShell";
import { ButtonLink } from "@/components/ui/Button";
import { ApplicationsTable } from "@/components/domain/ApplicationsTable";
import { ApplicationsFilterBar, EMPTY_APPLICATION_FILTERS } from "@/components/domain/ApplicationsFilterBar";
import { useApplications } from "@/hooks/useData";
import { useFilters } from "@/hooks/useFilters";

export default function OwnerApplications() {
  const filters = useFilters(EMPTY_APPLICATION_FILTERS);
  const { data, isLoading, isError, error, refetch } = useApplications(filters.query);

  return (
    <div>
      <PageHeader
        title="Applications"
        description="Track every verification application you've submitted."
        action={
          <ButtonLink to="/app/owner/applications/new">Apply for verification</ButtonLink>
        }
      />
      <ApplicationsFilterBar filters={filters} />
      <ApplicationsTable
        applications={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath="/app/owner/applications"
        emptyTitle={filters.active ? "No applications match" : undefined}
        emptyDescription={
          filters.active ? "Try a different search or clear the filters." : "Once you apply for verification on an instrument, it'll show up here."
        }
      />
    </div>
  );
}
