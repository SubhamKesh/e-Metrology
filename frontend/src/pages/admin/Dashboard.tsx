import { useState } from "react";
import { ActionCard, DashboardHero, Panel, SectionTitle, StatCard } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { useDashboard } from "@/hooks/useData";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/cn";
import { ROLE_LABEL } from "@/lib/types";
import type { AdminDashboard, OwnerDashboard, OfficerDashboard } from "@/lib/types";

type View = "admin" | "owner" | "lmo" | "gatc";

const VIEWS: { id: View; label: string; hint: string }[] = [
  { id: "admin", label: "System", hint: "Whole registry" },
  { id: "owner", label: "Owners", hint: "Business owner activity" },
  { id: "lmo", label: "LMO", hint: "Legal Metrology Officers" },
  { id: "gatc", label: "GATC", hint: "Approved test centres" },
];

const fmt = (n: number) => n.toLocaleString("en-IN");

export default function AdminDashboardPage() {
  const { user } = useAuth();
  const [view, setView] = useState<View>("admin");
  const { data, isLoading, isError, refetch } = useDashboard(view);
  const active = VIEWS.find((v) => v.id === view)!;

  return (
    <div>
      <DashboardHero
        roleLabel={ROLE_LABEL.admin}
        title="System overview"
        description={`National verification activity across the registry${user ? `, ${user.name.split(" ")[0]}` : ""}.`}
      />

      {/* Segmented view switcher — scrolls horizontally rather than wrapping on small phones */}
      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div role="tablist" aria-label="Dashboard view" className="inline-flex gap-1 rounded-lg border border-line bg-white p-1 shadow-panel">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              role="tab"
              type="button"
              aria-selected={view === v.id}
              onClick={() => setView(v.id)}
              className={cn(
                "h-10 min-w-[4.5rem] whitespace-nowrap rounded-md px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40",
                view === v.id ? "bg-teal text-white" : "text-slate-600 hover:bg-paper2",
              )}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-500">Showing: {active.hint}</p>

      <div className="mt-4" role="tabpanel">
        {isLoading ? (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
        ) : isError || !data ? (
          <ErrorState message="Couldn't load dashboard data." onRetry={() => refetch()} />
        ) : view === "admin" ? (
          <SystemView d={data as AdminDashboard} />
        ) : view === "owner" ? (
          <OwnerView d={data as OwnerDashboard} />
        ) : (
          <OfficerView d={data as OfficerDashboard} />
        )}
      </div>

      <SectionTitle>Manage</SectionTitle>
      <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4">
        <ActionCard to="/app/admin/users" title="Officer accounts" description="Approve and manage LMO and GATC accounts." />
        <ActionCard to="/app/admin/applications" title="Applications" description="Every verification application, filterable by status." />
        <ActionCard to="/app/admin/instruments" title="Instruments" description="All registered instruments across the registry." />
        <ActionCard to="/app/admin/certificates" title="Certificates" description="Issued certificates and their validity." />
        <ActionCard to="/app/admin/audit-log" title="Audit log" description="Sign-ins, password changes and admin actions." />
      </div>
    </div>
  );
}

function SystemView({ d }: { d: AdminDashboard }) {
  const rows = d.by_location.slice().sort((a, b) => b.count - a.count);
  const maxCount = Math.max(...rows.map((l) => l.count), 1);
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard label="Total instruments" value={fmt(d.total_instruments)} />
        <StatCard label="Verified" value={fmt(d.verified)} tone="success" />
        <StatCard label="Pending" value={fmt(d.pending)} tone="warning" />
        <StatCard label="Expired" value={fmt(d.expired)} tone="danger" />
      </div>
      {rows.length > 0 && (
        <Panel className="mt-6 p-4 sm:p-6">
          <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
            <h2 className="font-display text-lg text-ink">Instruments by state/UT</h2>
            <span className="text-xs text-slate-500">Grouped by the instrument's registered state</span>
          </div>
          <ul className="flex flex-col gap-3">
            {rows.map((row) => (
              <li key={row.state_code} className="grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-3 sm:grid-cols-[10rem_1fr_4rem]">
                <span className="truncate text-sm text-slate-600" title={row.state_name}>{row.state_name}</span>
                <div className="h-2.5 rounded-full bg-paper2" role="presentation">
                  <div className="h-2.5 rounded-full bg-teal" style={{ width: `${(row.count / maxCount) * 100}%` }} />
                </div>
                <span className="text-right text-sm tabular text-ink">{fmt(row.count)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </>
  );
}

function OwnerView({ d }: { d: OwnerDashboard }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      <StatCard label="Total instruments" value={fmt(d.total_instruments)} />
      <StatCard label="Verified" value={fmt(d.verified)} tone="success" />
      <StatCard label="Pending" value={fmt(d.pending)} tone="warning" />
      <StatCard label="Expired" value={fmt(d.expired)} tone="danger" />
    </div>
  );
}

function OfficerView({ d }: { d: OfficerDashboard }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      <StatCard label="Assigned" value={fmt(d.assigned)} />
      <StatCard label="Pending" value={fmt(d.pending)} tone="warning" />
      <StatCard label="Completed" value={fmt(d.completed)} tone="success" />
      <StatCard label="Today" value={fmt(d.today_inspections)} tone="info" />
    </div>
  );
}
