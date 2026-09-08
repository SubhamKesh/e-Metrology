import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { TextInput, SelectInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Card";
import { useCreateInstrument } from "@/hooks/useData";
import { ApiError } from "@/lib/api";

// Kept in sync with ALLOWED_INSTRUMENT_TYPES in the backend
// (app/models/instrument.py) — the backend rejects anything outside this
// exact set, so the dropdown here must offer only these values, spelled
// exactly the same way.
const INSTRUMENT_TYPE_OPTIONS = [
  { value: "Electronic Weighing Machine", label: "Electronic Weighing Machine" },
  { value: "Fuel Dispensing Unit", label: "Fuel Dispensing Unit" },
  { value: "Platform Scale", label: "Platform Scale" },
  { value: "Water Meter", label: "Water Meter" },
  { value: "Clinical Thermometer", label: "Clinical Thermometer" },
  { value: "Automatic Rail Weighbridge", label: "Automatic Rail Weighbridge" },
  { value: "Tape Measure", label: "Tape Measure" },
  { value: "Non-Automatic Weighing Instrument", label: "Non-Automatic Weighing Instrument" },
  { value: "Load Cell", label: "Load Cell" },
  { value: "Beam Scale", label: "Beam Scale" },
  { value: "Counter Machine", label: "Counter Machine" },
  { value: "Weights", label: "Weights" },
  { value: "Gas Meter", label: "Gas Meter" },
  { value: "Energy Meter", label: "Energy Meter" },
  { value: "Moisture Meter", label: "Moisture Meter" },
  { value: "Speed Meter", label: "Speed Meter" },
  { value: "Breath Analyser", label: "Breath Analyser" },
  { value: "Flow Meter", label: "Flow Meter" },
];

const EMPTY = { type: "", manufacturer: "", model: "", capacity: "", serial_no: "", location: "" };

export default function RegisterInstrument() {
  const navigate = useNavigate();
  const create = useCreateInstrument();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const instrument = await create.mutateAsync(form);
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
            placeholder="Select an instrument type"
            options={INSTRUMENT_TYPE_OPTIONS}
            value={form.type}
            onChange={(e) => set("type", e.target.value)}
          />
          <div className="grid grid-cols-2 gap-4">
            <TextInput label="Manufacturer" required value={form.manufacturer} onChange={(e) => set("manufacturer", e.target.value)} />
            <TextInput label="Model" required value={form.model} onChange={(e) => set("model", e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <TextInput label="Capacity" required placeholder="e.g. 30 kg" value={form.capacity} onChange={(e) => set("capacity", e.target.value)} />
            <TextInput label="Serial number" required value={form.serial_no} onChange={(e) => set("serial_no", e.target.value)} />
          </div>
          <TextInput
            label="Location"
            required
            placeholder="e.g. Baharampur, West Bengal"
            value={form.location}
            onChange={(e) => set("location", e.target.value)}
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