import { Link } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { StatCard } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";
import { useDashboard } from "@/hooks/useData";
import type { OfficerDashboard, Role } from "@/lib/types";
import { useAuth } from "@/context/AuthContext";

export default function OfficerDashboardPage({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const { user } = useAuth();
  const { data, isLoading, isError } = useDashboard(role);
  const d = data as OfficerDashboard | undefined;
  const base = `/app/${role}`;

  return (
    <div>
      <PageHeader
        title={`Welcome back, ${user?.name.split(" ")[0]}`}
        description="Your verification workload for today."
        action={
          <Link to={`${base}/queue`}>
            <Button>Open queue</Button>
          </Link>
        }
      />

      {isLoading ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : isError ? (
        <p className="text-sm text-danger">Couldn't load your dashboard. Try refreshing.</p>
      ) : d ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Assigned to you" value={d.assigned} />
          <StatCard label="Pending" value={d.pending} tone="warning" />
          <StatCard label="Completed" value={d.completed} tone="success" />
          <StatCard label="Today's inspections" value={d.today_inspections} />
        </div>
      ) : null}

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <Link to={`${base}/queue`} className="rounded-lg border border-line bg-white p-5 shadow-panel hover:shadow-raised">
          <p className="font-medium text-ink">Verification queue</p>
          <p className="mt-1 text-sm text-slate-500">Claim unassigned applications submitted by businesses.</p>
        </Link>
        <Link to={`${base}/assignments`} className="rounded-lg border border-line bg-white p-5 shadow-panel hover:shadow-raised">
          <p className="font-medium text-ink">My assignments</p>
          <p className="mt-1 text-sm text-slate-500">Applications currently assigned to you for inspection.</p>
        </Link>
      </div>
    </div>
  );
}
