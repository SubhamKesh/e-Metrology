import type { ReactNode } from "react";
import { Panel } from "@/components/ui/Card";
import { ApplicationStatusBadge } from "@/components/ui/StatusBadge";
import { LifecycleTimeline } from "./LifecycleTimeline";
import { useInstrument } from "@/hooks/useData";
import { Skeleton } from "@/components/ui/States";
import { LocationText } from "@/components/ui/LocationText";
import type { Application } from "@/lib/types";

export function ApplicationOverview({ application, actions }: { application: Application; actions?: ReactNode }) {
  const { data: instrument, isLoading } = useInstrument(application.instrument_id);

  return (
    <div className="max-w-3xl">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div>
          <p className="break-all font-mono text-xs text-slate-500">{application.id}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="font-display text-2xl text-ink sm:text-3xl">
              {isLoading ? <Skeleton className="h-7 w-40" /> : instrument?.type ?? "Instrument"}
            </h1>
            <ApplicationStatusBadge status={application.status} />
          </div>
        </div>
        {actions}
      </div>

      <Panel className="mb-6 p-4 sm:p-5">
        <LifecycleTimeline current={application.status} />
      </Panel>

      <Panel className="mb-6 p-4 sm:p-5">
        <h2 className="mb-3 text-sm font-medium text-ink">Instrument identity</h2>
        {isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : instrument ? (
          <dl className="grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
            <Field label="Manufacturer / Model" value={`${instrument.manufacturer} · ${instrument.model}`} />
            <Field label="UIID" value={instrument.uiid ?? instrument.serial_no} mono />
            <Field label="Capacity" value={instrument.capacity} />
            <Field label="Location" value={<LocationText location={instrument.location} />} />
          </dl>
        ) : (
          <p className="text-sm text-slate-500">Instrument details unavailable.</p>
        )}
      </Panel>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className={`mt-0.5 text-ink ${mono ? "font-mono text-xs" : ""}`}>{value}</dd>
    </div>
  );
}
