import { ExportButtons } from "@/components/domain/ExportButtons";
import { FilterBar } from "@/components/domain/FilterBar";
import { SelectInput, TextInput } from "@/components/ui/Field";
import { useInstrumentTypeSpecs } from "@/hooks/useData";
import type { FilterController } from "@/hooks/useFilters";
import { APPLICATION_STATUS_OPTIONS, APPLICATION_TYPE_OPTIONS, ANY } from "@/lib/filterOptions";

export const EMPTY_APPLICATION_FILTERS = {
  q: "",
  status: "",
  application_type: "",
  instrument_type: "",
  date_from: "",
  date_to: "",
};
export type ApplicationFilterState = typeof EMPTY_APPLICATION_FILTERS;

interface Props {
  filters: FilterController<ApplicationFilterState>;
  /** Hide the status filter where the list already has a fixed status (the officer queue). */
  showStatus?: boolean;
  /** Extra export parameters that are not filters, e.g. { mine: true } for "my assignments". */
  exportExtra?: object;
}

// Search + filters + export for any list of applications (owner, officer and admin).
export function ApplicationsFilterBar({ filters, showStatus = true, exportExtra }: Props) {
  const { data: specs } = useInstrumentTypeSpecs();
  const typeOptions = [ANY, ...(specs ?? []).map((s) => ({ value: s.type, label: s.type }))];
  const { values, set } = filters;
  return (
    <FilterBar
      search={values.q}
      onSearch={(v) => set("q", v)}
      searchLabel="Search applications"
      searchPlaceholder="UIID, serial number, manufacturer, model, certificate number or application ID"
      active={filters.active}
      onClear={filters.clear}
      dateError={filters.dateError}
      actions={<ExportButtons kind="applications" params={{ ...filters.query, ...exportExtra }} disabled={!!filters.dateError} />}
    >
      {showStatus && (
        <SelectInput label="Status" value={values.status} onChange={(e) => set("status", e.target.value)} options={APPLICATION_STATUS_OPTIONS} />
      )}
      <SelectInput label="Verification type" value={values.application_type} onChange={(e) => set("application_type", e.target.value)} options={APPLICATION_TYPE_OPTIONS} />
      <SelectInput label="Instrument type" value={values.instrument_type} onChange={(e) => set("instrument_type", e.target.value)} options={typeOptions} />
      <TextInput label="Applied from" type="date" value={values.date_from} onChange={(e) => set("date_from", e.target.value)} />
      <TextInput label="Applied to" type="date" value={values.date_to} onChange={(e) => set("date_to", e.target.value)} />
    </FilterBar>
  );
}
