import { useState } from "react";
import { PageHeader } from "@/components/layout/AppShell";
import { SelectInput } from "@/components/ui/Field";
import { ApplicationsTable } from "@/components/domain/ApplicationsTable";
import { useApplications } from "@/hooks/useData";
import type { ApplicationStatus } from "@/lib/types";
import { APPLICATION_STATUS_LABEL } from "@/components/ui/StatusBadge";

const STATUS_OPTIONS = Object.entries(APPLICATION_STATUS_LABEL).map(([value, label]) => ({ value, label }));

export default function AdminApplications() {
  const [status, setStatus] = useState<ApplicationStatus | "">("");
  const { data, isLoading, isError, error, refetch } = useApplications(status ? { status } : undefined);

  return (
    <div>
      <PageHeader title="All applications" description="Every verification application across the system." />
      <div className="mb-4 max-w-xs">
        <SelectInput
          label="Filter by status"
          placeholder="All statuses"
          value={status}
          onChange={(e) => setStatus(e.target.value as ApplicationStatus | "")}
          options={STATUS_OPTIONS}
        />
      </div>
      <ApplicationsTable
        applications={data}
        isLoading={isLoading}
        isError={isError}
        error={error}
        onRetry={refetch}
        basePath="/app/admin/applications"
      />
    </div>
  );
}
