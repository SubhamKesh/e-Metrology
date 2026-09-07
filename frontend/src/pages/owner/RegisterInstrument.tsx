
import { useState } from "react";
import type { FormEvent } from "react";

import { PageHeader } from "@/components/layout/AppShell";
import { TextInput, SelectInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Card";
import { useCreateInstrument } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import { INSTRUMENT_TYPES, type InstrumentType } from "@/lib/types";

const INSTRUMENT_TYPE_OPTIONS = INSTRUMENT_TYPES.map((t) => ({
  value: t,
  label: t,
}));

type FormState = {
  type: string;
  manufacturer: string;
  model: string;
  capacity: string;
  serial_no: string;
  location: string;
};

const EMPTY: FormState = {
  type: "",
  manufacturer: "",
  model: "",
  capacity: "",
  serial_no: "",
  location: "",
};

export default function RegisterInstrument() {
  const create = useCreateInstrument();

  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const navigate = (destination: string | number) => {
    if (typeof destination === "number") {
      window.history.go(destination);
    } else {
      window.location.assign(destination);
    }
  };

  function setField<K extends keyof FormState>(key: K, value: string) {
    setForm((current) => ({
      ...current,
      [key]: value,
    }));
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    try {
      const instrument = await create.mutateAsync({
        ...form,
        type: form.type as InstrumentType,
      });

      navigate(`/app/owner/instruments/${instrument.id}`);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setError(
          "An instrument with this serial number is already registered in the system.",
        );
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Something went wrong. Try again.");
      }
    }
  }

  return (
    <div className="max-w-xl">
      <PageHeader
        title="Register instrument"
        description="Add a new weighing or measuring instrument to your account."
      />

      <Panel className="p-6">
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-4"
        >
          <SelectInput
            label="Instrument type"
            required
            placeholder="Select an instrument type"
            options={INSTRUMENT_TYPE_OPTIONS}
            value={form.type}
            onChange={(e) => setField("type", e.target.value)}
          />

          <div className="grid grid-cols-2 gap-4">
            <TextInput
              label="Manufacturer"
              required
              value={form.manufacturer}
              onChange={(e) =>
                setField("manufacturer", e.target.value)
              }
            />

            <TextInput
              label="Model"
              required
              value={form.model}
              onChange={(e) =>
                setField("model", e.target.value)
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <TextInput
              label="Capacity"
              required
              placeholder="e.g. 30 kg"
              value={form.capacity}
              onChange={(e) =>
                setField("capacity", e.target.value)
              }
            />

            <TextInput
              label="Serial number"
              required
              value={form.serial_no}
              onChange={(e) =>
                setField("serial_no", e.target.value)
              }
            />
          </div>

          <TextInput
            label="Location"
            required
            placeholder="e.g. Baharampur, West Bengal"
            value={form.location}
            onChange={(e) =>
              setField("location", e.target.value)
            }
          />

          {error && (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          )}

          <div className="mt-2 flex gap-3">
            <Button
              type="submit"
              loading={create.isPending}
            >
              Register instrument
            </Button>

            <Button
              type="button"
              variant="secondary"
              onClick={() => navigate(-1)}
              disabled={create.isPending}
            >
              Cancel
            </Button>
          </div>
        </form>
      </Panel>
    </div>
  );
}

