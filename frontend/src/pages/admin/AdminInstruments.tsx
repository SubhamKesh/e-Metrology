import { useState } from "react";
import { PageHeader } from "@/components/layout/AppShell";
import { TextInput } from "@/components/ui/Field";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/States";
import { useInstruments } from "@/hooks/useData";
import type { Instrument } from "@/lib/types";
import { ApiError } from "@/lib/api";

export default function AdminInstruments() {
  const [ownerId, setOwnerId] = useState("");
  const { data, isLoading, isError, error, refetch } = useInstruments(ownerId ? { owner_id: ownerId } : undefined);

  const columns: Column<Instrument>[] = [
    { header: "Type", cell: (i) => i.type },
    { header: "Manufacturer / Model", cell: (i) => `${i.manufacturer} · ${i.model}` },
    { header: "Serial no.", cell: (i) => <span className="font-mono text-xs">{i.uiid}</span> },
    { header: "Location", cell: (i) => i.location },
    { header: "Owner ID", cell: (i) => <span className="font-mono text-xs text-slate-400">{i.owner_id.slice(0, 10)}…</span> },
  ];

  return (
    <div>
      <PageHeader title="All instruments" description="Every instrument registered in the system." />
      <div className="mb-4 max-w-xs">
        <TextInput
          label="Filter by owner ID"
          placeholder="Paste an owner user ID"
          value={ownerId}
          onChange={(e) => setOwnerId(e.target.value)}
        />
      </div>
      {isError ? (
        <ErrorState message={error instanceof ApiError ? error.message : "Please try again."} onRetry={refetch} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-line bg-white">
          <DataTable columns={columns} rows={data ?? []} rowKey={(r) => r.id} isLoading={isLoading} emptyTitle="No instruments found" />
        </div>
      )}
    </div>
  );
}
