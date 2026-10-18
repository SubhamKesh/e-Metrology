import { ExportButtons } from "@/components/domain/ExportButtons";
import { FilterBar } from "@/components/domain/FilterBar";
import { SelectInput, TextInput } from "@/components/ui/Field";
import { useInstrumentTypeSpecs } from "@/hooks/useData";
import type { FilterController } from "@/hooks/useFilters";
import { ANY, APPLICATION_TYPE_OPTIONS, CERTIFICATE_STATUS_OPTIONS } from "@/lib/filterOptions";

export const EMPTY_CERTIFICATE_FILTERS = {
  q: "",
  status: "",
  application_type: "",
  instrument_type: "",
  date_from: "",
  date_to: "",
};
export type CertificateFilterState = typeof EMPTY_CERTIFICATE_FILTERS;

// Search + filters + export for any list of certificates.
export function CertificatesFilterBar({ filters }: { filters: FilterController<CertificateFilterState> }) {
  const { data: specs } = useInstrumentTypeSpecs();
  const typeOptions = [ANY, ...(specs ?? []).map((s) => ({ value: s.type, label: s.type }))];
  const { values, set } = filters;
  return (
    <FilterBar
      search={values.q}
      onSearch={(v) => set("q", v)}
      searchLabel="Search certificates"
      searchPlaceholder="Certificate number, seal number, UIID, serial number, manufacturer or model"
      active={filters.active}
      onClear={filters.clear}
      dateError={filters.dateError}
      actions={<ExportButtons kind="certificates" params={filters.query} disabled={!!filters.dateError} />}
    >
      <SelectInput label="Validity" value={values.status} onChange={(e) => set("status", e.target.value)} options={CERTIFICATE_STATUS_OPTIONS} />
      <SelectInput label="Verification type" value={values.application_type} onChange={(e) => set("application_type", e.target.value)} options={APPLICATION_TYPE_OPTIONS} />
      <SelectInput label="Instrument type" value={values.instrument_type} onChange={(e) => set("instrument_type", e.target.value)} options={typeOptions} />
      <TextInput label="Issued from" type="date" value={values.date_from} onChange={(e) => set("date_from", e.target.value)} />
      <TextInput label="Issued to" type="date" value={values.date_to} onChange={(e) => set("date_to", e.target.value)} />
    </FilterBar>
  );
}
