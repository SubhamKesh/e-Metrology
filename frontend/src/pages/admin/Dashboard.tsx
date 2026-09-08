import { PageHeader } from "@/components/layout/AppShell";
import { StatCard, Panel } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { useDashboard } from "@/hooks/useData";
import type { AdminDashboard, OwnerDashboard, OfficerDashboard } from "@/lib/types";
import { useState } from "react";

type View = "admin" | "owner" | "lmo" | "gatc";

export default function AdminDashboardPage() {
  const [view, setView] = useState<View>("admin");
  const { data, isLoading, isError } = useDashboard(view);

  // Render depending on the selected view
  if (isLoading) {
    return (
      <div>
        <PageHeader title="System overview" description="National verification activity across the registry." />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4 mt-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="System overview" description="National verification activity across the registry." />
        <p className="text-sm text-danger mt-4">Couldn't load dashboard data. Try refreshing.</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="System overview" description="National verification activity across the registry." />

      <div className="mt-4 flex gap-3">
        <button
          onClick={() => setView("admin")}
          className={`rounded-md px-3 py-1 text-sm ${view === "admin" ? "bg-teal text-white" : "bg-paper"}`}>
          System
        </button>
        <button
          onClick={() => setView("owner")}
          className={`rounded-md px-3 py-1 text-sm ${view === "owner" ? "bg-teal text-white" : "bg-paper"}`}>
          Owners
        </button>
        <button
          onClick={() => setView("lmo")}
          className={`rounded-md px-3 py-1 text-sm ${view === "lmo" ? "bg-teal text-white" : "bg-paper"}`}>
          LMO
        </button>
        <button
          onClick={() => setView("gatc")}
          className={`rounded-md px-3 py-1 text-sm ${view === "gatc" ? "bg-teal text-white" : "bg-paper"}`}>
          GATC
        </button>
      </div>

      <div className="mt-4">
        {view === "admin" && data ? (
          (() => {
            const d = data as AdminDashboard;
            const maxCount = d ? Math.max(...d.by_location.map((l) => l.count), 1) : 1;
            return (
              <>
                <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                  <StatCard label="Total instruments" value={d.total_instruments.toLocaleString("en-IN")} />
                  <StatCard label="Verified" value={d.verified.toLocaleString("en-IN")} tone="success" />
                  <StatCard label="Pending" value={d.pending.toLocaleString("en-IN")} tone="warning" />
                  <StatCard label="Expired" value={d.expired.toLocaleString("en-IN")} tone="danger" />
                </div>

                {d.by_location.length > 0 && (
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
              </>
            );
          })()
        ) : view === "owner" && data ? (
          (() => {
            const d = data as OwnerDashboard;
            return (
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <StatCard label="Total instruments" value={d.total_instruments.toLocaleString("en-IN")} />
                <StatCard label="Verified" value={d.verified.toLocaleString("en-IN")} tone="success" />
                <StatCard label="Pending" value={d.pending.toLocaleString("en-IN")} tone="warning" />
                <StatCard label="Expired" value={d.expired.toLocaleString("en-IN")} tone="danger" />
              </div>
            );
          })()
        ) : (view === "lmo" || view === "gatc") && data ? (
          (() => {
            const d = data as OfficerDashboard;
            return (
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <StatCard label="Assigned" value={d.assigned.toLocaleString("en-IN")} />
                <StatCard label="Pending" value={d.pending.toLocaleString("en-IN")} tone="warning" />
                <StatCard label="Completed" value={d.completed.toLocaleString("en-IN")} tone="success" />
                <StatCard label="Today" value={d.today_inspections.toLocaleString("en-IN")} />
              </div>
            );
          })()
        ) : null}
      </div>
    </div>
  );
}
