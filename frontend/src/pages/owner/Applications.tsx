import { Link } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { ApplicationsTable } from "@/components/domain/ApplicationsTable";
import { useApplications } from "@/hooks/useData";

export default function OwnerApplications() {
  const { data, isLoading, isError, error, refetch } = useApplications();

  return (
    <div>
      <PageHeader
        title="Applications"
        description="Track every verification application you've submitted."
        action={
          <Link to="/app/owner/applications/new">
            <Button>Apply for verification</Button>
          </Link>
        }
      />
      <ApplicationsTable
        applications={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath="/app/owner/applications"
        emptyDescription="Once you apply for verification on an instrument, it'll show up here."
      />
    </div>
  );
}
