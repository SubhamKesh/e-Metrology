import type { ReactNode } from "react";
import { Panel } from "@/components/ui/Card";
import { AddToCalendar } from "./AddToCalendar";
import { formatScheduleDate, slotLabel } from "@/lib/schedule";
import type { Application, Instrument, ScheduleHistoryEntry } from "@/lib/types";

const KIND_LABEL: Record<ScheduleHistoryEntry["kind"], string> = {
  scheduled: "Booked",
  assigned: "Assigned by admin",
  rescheduled: "Rescheduled",
  reassigned: "Reassigned to another officer",
};

/** The booked inspection date and slot, its change history and the Add-to-calendar buttons. */
export function ScheduleCard({
  application,
  instrument,
  actions,
}: {
  application: Application;
  instrument?: Instrument;
  actions?: ReactNode;
}) {
  if (!application.scheduled_date || !application.slot) return null;
  const upcoming = application.status === "scheduled";
  const history = application.schedule_history ?? [];

  return (
    <Panel className="mb-6 p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="mb-1 text-sm font-medium text-ink">{upcoming ? "Inspection scheduled" : "Inspection date"}</h2>
          <p className="text-lg font-medium text-ink">{formatScheduleDate(application.scheduled_date)}</p>
          <p className="text-sm text-slate-600">{slotLabel(application.slot, application.slot_label)}</p>
        </div>
        {actions}
      </div>

      {upcoming && (
        <div className="mt-4">
          <AddToCalendar application={application} instrument={instrument} />
        </div>
      )}

      {history.length > 1 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-slate-600">Schedule history ({history.length})</summary>
          <ul className="mt-2 space-y-1.5 text-slate-600">
            {[...history].reverse().map((h, i) => (
              <li key={`${h.at}-${i}`}>
                <span className="font-medium text-ink">{KIND_LABEL[h.kind] ?? h.kind}</span>:{" "}
                {formatScheduleDate(h.date)}, {h.slot}
                {h.previous_date && ` (was ${formatScheduleDate(h.previous_date)}${h.previous_slot ? `, ${h.previous_slot}` : ""})`}
                {h.reason && <span className="text-slate-500"> — {h.reason}</span>}
                <span className="block text-xs text-slate-500">{new Date(h.at).toLocaleString("en-IN")}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}
