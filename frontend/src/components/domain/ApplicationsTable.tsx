import { useNavigate } from "react-router-dom";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ApplicationStatusBadge } from "@/components/ui/StatusBadge";
import { ErrorState } from "@/components/ui/States";
import { useInstruments } from "@/hooks/useData";
import type { Application } from "@/lib/types";
import { ApiError } from "@/lib/api";

interface Props {
  applications?: Application[];
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  onRetry: () => void;
  basePath: string;
  emptyTitle?: string;
  emptyDescription?: string;
}

export function ApplicationsTable({
  applications,
  isLoading,
  isError,
  error,
  onRetry,
  basePath,
  emptyTitle = "No applications yet",
  emptyDescription,
}: Props) {
  const navigate = useNavigate();
  // Instrument info isn't joined onto the application list response, so we
  // resolve type/serial from a parallel instruments fetch when available
  // (owner/admin can list instruments; officers just see the ID, which is
  // still correct — never fabricate instrument fields we don't have).
  const { data: instruments } = useInstruments();
  const instrumentMap = new Map((instruments ?? []).map((i) => [i.id, i]));

  if (isError) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Please try again."} onRetry={onRetry} />;
  }

  const columns: Column<Application>[] = [
    {
      header: "Application",
      cell: (a) => <span className="font-mono text-xs text-slate-500">{a.id.slice(0, 10)}…</span>,
    },
    {
      header: "Instrument",
      cell: (a) => {
        const i = instrumentMap.get(a.instrument_id);
        return i ? `${i.type} · ${i.serial_no}` : <span className="text-slate-400">{a.instrument_id.slice(0, 10)}…</span>;
      },
    },
    { header: "Status", cell: (a) => <ApplicationStatusBadge status={a.status} /> },
  ];

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-white">
      <DataTable
        columns={columns}
        rows={applications ?? []}
        rowKey={(a) => a.id}
        isLoading={isLoading}
        onRowClick={(a) => navigate(`${basePath}/${a.id}`)}
        emptyTitle={emptyTitle}
        emptyDescription={emptyDescription}
      />
    </div>
  );
}
