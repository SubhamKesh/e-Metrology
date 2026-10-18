import { PageHeader } from "@/components/layout/AppShell";
import { ExportButtons } from "@/components/domain/ExportButtons";
import { FilterBar } from "@/components/domain/FilterBar";
import { SelectInput, TextInput } from "@/components/ui/Field";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/States";
import { LocationText } from "@/components/ui/LocationText";
import { useGeoDistricts, useGeoStates, useInstruments, useInstrumentTypeSpecs } from "@/hooks/useData";
import { useFilters } from "@/hooks/useFilters";
import { ANY } from "@/lib/filterOptions";
import type { Instrument } from "@/lib/types";
import { ApiError } from "@/lib/api";

export default function AdminInstruments() {
  const filters = useFilters({ q: "", type: "", state_code: "", district_code: "", owner_id: "" });
  const { values, set } = filters;
  const { data, isLoading, isError, error, refetch } = useInstruments(filters.query);
  const { data: specs } = useInstrumentTypeSpecs();
  const { data: states } = useGeoStates();
  const { data: districts } = useGeoDistricts(values.state_code || undefined);

  const columns: Column<Instrument>[] = [
    { header: "Type", cell: (i) => i.type },
    { header: "Manufacturer / Model", cell: (i) => `${i.manufacturer} · ${i.model}` },
    { header: "UIID", cell: (i) => <span className="font-mono text-xs">{i.uiid}</span> },
    { header: "Serial no.", cell: (i) => <span className="font-mono text-xs">{i.serial_no}</span> },
    { header: "Location", cell: (i) => <LocationText location={i.location} /> },
    { header: "Owner ID", cell: (i) => <span className="font-mono text-xs text-slate-500">{i.owner_id.slice(0, 10)}…</span> },
  ];

  return (
    <div>
      <PageHeader title="All instruments" description="Every instrument registered in the system. Search, filter and export what you see." />
      <FilterBar
        search={values.q}
        onSearch={(v) => set("q", v)}
        searchLabel="Search instruments"
        searchPlaceholder="UIID, serial number, manufacturer, model or type"
        active={filters.active}
        onClear={filters.clear}
        actions={<ExportButtons kind="instruments" params={filters.query} />}
      >
        <SelectInput
          label="Instrument type"
          value={values.type}
          onChange={(e) => set("type", e.target.value)}
          options={[ANY, ...(specs ?? []).map((s) => ({ value: s.type, label: s.type }))]}
        />
        <SelectInput
          label="State / UT"
          value={values.state_code}
          onChange={(e) => {
            set("state_code", e.target.value);
            set("district_code", "");
          }}
          options={[ANY, ...(states ?? []).map((s) => ({ value: s.code, label: s.name }))]}
        />
        <SelectInput
          label="District"
          value={values.district_code}
          disabled={!values.state_code}
          onChange={(e) => set("district_code", e.target.value)}
          options={[ANY, ...(districts ?? []).map((d) => ({ value: d.code, label: d.name }))]}
        />
        <TextInput
          label="Owner ID"
          placeholder="Paste an owner user ID"
          value={values.owner_id}
          onChange={(e) => set("owner_id", e.target.value.trim())}
        />
      </FilterBar>
      {isError ? (
        <ErrorState message={error instanceof ApiError ? error.message : "Please try again."} onRetry={refetch} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-line bg-white">
          <DataTable
            columns={columns}
            rows={data ?? []}
            rowKey={(r) => r.id}
            isLoading={isLoading}
            emptyTitle={filters.active ? "No instruments match" : "No instruments found"}
            emptyDescription={filters.active ? "Try a different search or clear the filters." : undefined}
          />
        </div>
      )}
    </div>
  );
}
