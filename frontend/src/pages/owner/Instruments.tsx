import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { ButtonLink } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/States";
import { LocationText } from "@/components/ui/LocationText";
import { useInstruments } from "@/hooks/useData";
import type { Instrument } from "@/lib/types";
import { ApiError } from "@/lib/api";

export default function OwnerInstruments() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error, refetch } = useInstruments();

  const columns: Column<Instrument>[] = [
    { header: "Type", cell: (i) => i.type },
    { header: "Manufacturer / Model", cell: (i) => `${i.manufacturer} · ${i.model}` },
    { header: "UIID", cell: (i) => <span className="font-mono text-xs">{i.uiid}</span> },
    { header: "Capacity", cell: (i) => i.capacity },
    { header: "Location", cell: (i) => <LocationText location={i.location} /> },
  ];

  return (
    <div>
      <PageHeader
        title="My instruments"
        description="Every instrument registered under your account."
        action={
          <ButtonLink to="/app/owner/instruments/new">Register instrument</ButtonLink>
        }
      />
      {isError ? (
        <ErrorState message={error instanceof ApiError ? error.message : "Please try again."} onRetry={refetch} />
      ) : (
        <div className="md:overflow-hidden md:rounded-xl md:border md:border-line md:bg-white md:shadow-panel">
          <DataTable
            columns={columns}
            rows={data ?? []}
            rowKey={(r) => r.id}
            isLoading={isLoading}
            onRowClick={(r) => navigate(`/app/owner/instruments/${r.id}`)}
            emptyTitle="No instruments yet"
            emptyDescription="Register your first weighing or measuring instrument to get started."
          />
        </div>
      )}
    </div>
  );
}
