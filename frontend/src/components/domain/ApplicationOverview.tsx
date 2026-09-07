import type { ReactNode } from "react";
import { Panel } from "@/components/ui/Card";
import { ApplicationStatusBadge } from "@/components/ui/StatusBadge";
import { LifecycleTimeline } from "./LifecycleTimeline";
import { useInstrument } from "@/hooks/useData";
import { Skeleton } from "@/components/ui/States";
import type { Application } from "@/lib/types";

export function ApplicationOverview({ application, actions }: { application: Application; actions?: ReactNode }) {
  const { data: instrument, isLoading } = useInstrument(application.instrument_id);

  return (
    <div className="max-w-2xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-slate-400">{application.id}</p>
          <div className="mt-1 flex items-center gap-2">
            <h1 className="font-display text-2xl text-ink">
              {isLoading ? <Skeleton className="h-7 w-40" /> : instrument?.type ?? "Instrument"}
            </h1>
            <ApplicationStatusBadge status={application.status} />
          </div>
        </div>
        {actions}
      </div>

      <Panel className="mb-6 p-5">
        <LifecycleTimeline current={application.status} />
      </Panel>

      <Panel className="mb-6 p-5">
        <h2 className="mb-3 text-sm font-medium text-ink">Instrument identity</h2>
        {isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : instrument ? (
          <dl className="grid grid-cols-2 gap-y-3 text-sm">
            <Field label="Manufacturer / Model" value={`${instrument.manufacturer} · ${instrument.model}`} />
            <Field label="UIID" value={instrument.uiid ?? instrument.serial_no} mono />
            <Field label="Capacity" value={instrument.capacity} />
            <Field label="Location" value={instrument.location} />
          </dl>
        ) : (
          <p className="text-sm text-slate-400">Instrument details unavailable.</p>
        )}
      </Panel>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={`mt-0.5 text-ink ${mono ? "font-mono text-xs" : ""}`}>{value}</dd>
    </div>
  );
}
