import { useNavigate } from "react-router-dom";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/StatusBadge";
import { ErrorState } from "@/components/ui/States";
import type { Certificate } from "@/lib/types";
import { ApiError } from "@/lib/api";

export function CertificatesTable({
  certificates,
  isLoading,
  isError,
  error,
  onRetry,
  basePath,
}: {
  certificates?: Certificate[];
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  onRetry: () => void;
  basePath: string;
}) {
  const navigate = useNavigate();

  if (isError) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Please try again."} onRetry={onRetry} />;
  }

  const columns: Column<Certificate>[] = [
    { header: "Certificate ID", cell: (c) => <span className="font-mono text-xs">{c.id}</span> },
    {
      header: "Verified on",
      cell: (c) => new Date(c.verified_on).toLocaleDateString("en-IN", { dateStyle: "medium" }),
    },
    {
      header: "Valid until",
      cell: (c) => new Date(c.valid_until).toLocaleDateString("en-IN", { dateStyle: "medium" }),
    },
    { header: "Status", cell: (c) => <Badge tone={c.is_expired ? "danger" : "success"}>{c.is_expired ? "Expired" : "Valid"}</Badge> },
  ];

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-white">
      <DataTable
        columns={columns}
        rows={certificates ?? []}
        rowKey={(c) => c.id}
        isLoading={isLoading}
        onRowClick={(c) => navigate(`${basePath}/${c.id}`)}
        emptyTitle="No certificates yet"
        emptyDescription="Certificates appear here once an instrument passes verification."
      />
    </div>
  );
}
