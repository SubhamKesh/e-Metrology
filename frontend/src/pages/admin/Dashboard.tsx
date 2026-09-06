import { PageHeader } from "@/components/layout/AppShell";
import { StatCard, Panel } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { useDashboard } from "@/hooks/useData";
import type { AdminDashboard } from "@/lib/types";

export default function AdminDashboardPage() {
  const { data, isLoading, isError } = useDashboard("admin");
  const d = data as AdminDashboard | undefined;
  const maxCount = d ? Math.max(...d.by_location.map((l) => l.count), 1) : 1;

  return (
    <div>
      <PageHeader title="System overview" description="National verification activity across the registry." />

      {isLoading ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : isError ? (
        <p className="text-sm text-danger">Couldn't load dashboard data. Try refreshing.</p>
      ) : d ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Total instruments" value={d.total_instruments.toLocaleString("en-IN")} />
          <StatCard label="Verified" value={d.verified.toLocaleString("en-IN")} tone="success" />
          <StatCard label="Pending" value={d.pending.toLocaleString("en-IN")} tone="warning" />
          <StatCard label="Expired" value={d.expired.toLocaleString("en-IN")} tone="danger" />
        </div>
      ) : null}

      {d && d.by_location.length > 0 && (
        <Panel className="mt-6 p-6">
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="font-display text-lg text-ink">Instruments by location</h2>
            <span className="text-xs text-slate-400">Grouped on the instrument's free-text location field</span>
          </div>
          <div className="flex flex-col gap-3">
            {d.by_location
              .slice()
              .sort((a, b) => b.count - a.count)
              .map((row) => (
                <div key={row.location} className="flex items-center gap-3">
                  <span className="w-32 shrink-0 truncate text-sm text-slate-600">{row.location}</span>
                  <div className="h-2.5 flex-1 rounded-full bg-paper2">
                    <div
                      className="h-2.5 rounded-full bg-teal"
                      style={{ width: `${(row.count / maxCount) * 100}%` }}
                    />
                  </div>
                  <span className="w-16 shrink-0 text-right text-sm tabular text-ink">
                    {row.count.toLocaleString("en-IN")}
                  </span>
                </div>
              ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
