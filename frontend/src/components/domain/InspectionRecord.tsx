import { Panel } from "@/components/ui/Card";
import { InspectionResultBadge } from "@/components/ui/StatusBadge";
import { Skeleton } from "@/components/ui/States";
import { useApplicationInspection } from "@/hooks/useData";
import type { Application, ApplicationStatus } from "@/lib/types";

const AFTER_INSPECTION: ApplicationStatus[] = ["inspected", "certified", "rejected", "expiring", "expired"];

const num = (n: number) => String(Number(n.toFixed(4)));
const signed = (n: number) => `${n > 0 ? "+" : ""}${num(n)}`;

/** What the officer recorded: result, seal number, test readings with their error, and the checks. */
export function InspectionRecord({ application }: { application: Application }) {
  const show = AFTER_INSPECTION.includes(application.status);
  const { data: inspection, isLoading } = useApplicationInspection(application.id, show);
  if (!show) return null;
  if (isLoading) return <Skeleton className="mb-6 h-32 w-full" />;
  if (!inspection) return null;

  const unit = inspection.form?.unit ?? "";
  const points = inspection.test_points ?? [];
  const checks = inspection.checks ?? [];

  return (
    <Panel className="mb-6 p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium text-ink">Inspection record</h2>
        <InspectionResultBadge result={inspection.result} />
      </div>

      <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Inspected on</dt>
          <dd className="mt-0.5 text-ink">
            {inspection.created_at ? new Date(inspection.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—"}
            {inspection.submitted_offline && <span className="text-slate-500"> · recorded offline</span>}
          </dd>
        </div>
        {inspection.seal_number && (
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Seal / stamp number</dt>
            <dd className="mt-0.5 font-mono text-xs text-ink">{inspection.seal_number}</dd>
          </div>
        )}
      </dl>

      {points.length > 0 && inspection.form && (
        <div className="mt-4">
          <h3 className="mb-2 text-xs uppercase tracking-wide text-slate-500">{inspection.form.test_title}</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-1 pr-3 font-normal">{inspection.form.reference_label}</th>
                  <th className="py-1 pr-3 font-normal">{inspection.form.indicated_label}</th>
                  <th className="py-1 font-normal">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {points.map((p, i) => (
                  <tr key={i}>
                    <td className="py-1.5 pr-3 text-ink">{num(p.reference)} {unit}</td>
                    <td className="py-1.5 pr-3 text-ink">{num(p.indicated)} {unit}</td>
                    <td className="py-1.5 text-ink">
                      {signed(p.error)} {unit}
                      {p.error_pct !== null && <span className="text-slate-500"> ({signed(p.error_pct)}%)</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {checks.length > 0 && (
        <ul className="mt-4 space-y-1.5 text-sm">
          {checks.map((c) => (
            <li key={c.key} className="flex gap-2">
              <span aria-label={c.ok ? "Yes" : "No"} className={c.ok ? "text-success" : "text-danger"}>
                {c.ok ? "✓" : "✕"}
              </span>
              <span className="text-ink">{c.label}</span>
            </li>
          ))}
        </ul>
      )}

      {inspection.observations && (
        <div className="mt-4">
          <h3 className="mb-1 text-xs uppercase tracking-wide text-slate-500">Officer's notes</h3>
          <p className="whitespace-pre-wrap text-sm text-ink">{inspection.observations}</p>
        </div>
      )}
    </Panel>
  );
}
