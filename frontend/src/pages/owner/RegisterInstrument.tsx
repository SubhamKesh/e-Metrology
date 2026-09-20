import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { TextInput, SelectInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Card";
import { useCreateInstrument, useGeoDistricts, useGeoStates, useInstrumentTypeSpecs } from "@/hooks/useData";
import { ApiError } from "@/lib/api";

const EMPTY = {
  type: "",
  manufacturer: "",
  model: "",
  capacityValue: "",
  serial_no: "",
  state_code: "",
  district_code: "",
  address_line: "",
};

export default function RegisterInstrument() {
  const navigate = useNavigate();
  const create = useCreateInstrument();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);

  // Type list + capacity unit/input widget both come from the backend
  // (app/config/instrument_specs.py via GET /instruments/meta/types) —
  // no separate hardcoded list to keep in sync here.
  const { data: typeSpecs, isLoading: typesLoading } = useInstrumentTypeSpecs();
  const { data: states, isLoading: statesLoading } = useGeoStates();
  const { data: districts, isLoading: districtsLoading } = useGeoDistricts(form.state_code || undefined);

  const typeOptions = useMemo(
    () => (typeSpecs ?? []).map((s) => ({ value: s.type, label: s.type })),
    [typeSpecs],
  );
  const stateOptions = useMemo(
    () => (states ?? []).map((s) => ({ value: s.code, label: s.name })),
    [states],
  );
  const districtOptions = useMemo(
    () => (districts ?? []).map((d) => ({ value: d.code, label: d.name })),
    [districts],
  );

  const selectedSpec = typeSpecs?.find((s) => s.type === form.type);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  // Changing the state clears any previously-selected district — it
  // belonged to a different state's list and is no longer valid.
  function setState(stateCode: string) {
    setForm((f) => ({ ...f, state_code: stateCode, district_code: "" }));
  }

  // If the instrument type changes, the old numeric value was in a
  // different unit (e.g. switching from Energy Meter/kWh to Water
  // Meter/m³) — clear it rather than silently keep a now-meaningless
  // number under the new unit.
  useEffect(() => {
    setForm((f) => ({ ...f, capacityValue: "" }));
  }, [form.type]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const instrument = await create.mutateAsync({
        type: form.type,
        manufacturer: form.manufacturer,
        model: form.model,
        capacity: selectedSpec ? `${form.capacityValue} ${selectedSpec.unit}` : form.capacityValue,
        serial_no: form.serial_no,
        location: {
          state_code: form.state_code,
          district_code: form.district_code,
          address_line: form.address_line,
        },
      });
      navigate(`/app/owner/instruments/${instrument.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("This instrument couldn't be registered — please try again.");
      } else {
        setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
      }
    }
  }

  return (
    <div className="max-w-xl">
      <PageHeader title="Register instrument" description="Add a new weighing or measuring instrument to your account." />
      <Panel className="p-6">
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <SelectInput
            label="Instrument type"
            required
            placeholder={typesLoading ? "Loading instrument types…" : "Select an instrument type"}
            options={typeOptions}
            value={form.type}
            onChange={(e) => set("type", e.target.value)}
          />
          <div className="grid grid-cols-2 gap-4">
            <TextInput label="Manufacturer" required value={form.manufacturer} onChange={(e) => set("manufacturer", e.target.value)} />
            <TextInput label="Model" required value={form.model} onChange={(e) => set("model", e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <TextInput
              label={selectedSpec ? `Capacity (${selectedSpec.unit})` : "Capacity"}
              required
              type={selectedSpec?.input_type ?? "text"}
              step={selectedSpec?.step}
              min="0"
              disabled={!form.type}
              placeholder={selectedSpec?.placeholder ?? "Select a type first"}
              value={form.capacityValue}
              onChange={(e) => set("capacityValue", e.target.value)}
            />
            <TextInput label="Serial number" required value={form.serial_no} onChange={(e) => set("serial_no", e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <SelectInput
              label="State / UT"
              required
              placeholder={statesLoading ? "Loading states…" : "Select a state or UT"}
              options={stateOptions}
              value={form.state_code}
              onChange={(e) => setState(e.target.value)}
            />
            <SelectInput
              label="District"
              required
              disabled={!form.state_code}
              placeholder={
                !form.state_code ? "Select a state first" : districtsLoading ? "Loading districts…" : "Select a district"
              }
              options={districtOptions}
              value={form.district_code}
              onChange={(e) => set("district_code", e.target.value)}
            />
          </div>
          <TextInput
            label="Address"
            required
            placeholder="e.g. 12 Market Road"
            value={form.address_line}
            onChange={(e) => set("address_line", e.target.value)}
          />

          {error && <p className="text-sm text-danger">{error}</p>}
          <div className="mt-2 flex gap-3">
            <Button type="submit" loading={create.isPending}>
              Register instrument
            </Button>
            <Button type="button" variant="secondary" onClick={() => navigate(-1)}>
              Cancel
            </Button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
