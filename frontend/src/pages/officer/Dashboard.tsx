import { ActionCard, DashboardHero, SectionTitle, StatCard } from "@/components/ui/Card";
import { Badge } from "@/components/ui/StatusBadge";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { useApplications, useDashboard } from "@/hooks/useData";
import type { OfficerDashboard, Role } from "@/lib/types";
import { ROLE_LABEL } from "@/lib/types";
import { useAuth } from "@/context/AuthContext";

export default function OfficerDashboardPage({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const { user } = useAuth();
  const { data, isLoading, isError, refetch } = useDashboard(role);
  // Same query key as the shell's queue poller, so this is served from cache.
  const { data: queue } = useApplications({ status: "submitted" });
  const queueCount = Array.isArray(queue) ? queue.length : undefined;
  const d = data as OfficerDashboard | undefined;
  const base = `/app/${role}`;

  return (
    <div>
      {/* The primary "Verification queue" action lives in the top bar; no duplicate button here. */}
      <DashboardHero
        roleLabel={ROLE_LABEL[role]}
        title={`Welcome back, ${user?.name.split(" ")[0] ?? ""}`}
        description="Your verification workload for today."
      />

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState message="Couldn't load your dashboard." onRetry={() => refetch()} />
      ) : d ? (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          <StatCard label="Assigned to you" value={d.assigned} to={`${base}/assignments`} />
          <StatCard label="Pending" value={d.pending} tone="warning" to={`${base}/assignments`} />
          <StatCard label="Completed" value={d.completed} tone="success" />
          <StatCard label="Today's inspections" value={d.today_inspections} tone="info" />
        </div>
      ) : null}

      <SectionTitle>Where to start</SectionTitle>
      <div className="grid gap-3 sm:grid-cols-2 sm:gap-4">
        <ActionCard
          to={`${base}/queue`}
          title="Verification queue"
          description="Claim unassigned applications submitted by businesses."
          primary
          badge={queueCount !== undefined ? <Badge tone="info">{queueCount} waiting</Badge> : undefined}
        />
        <ActionCard
          to={`${base}/assignments`}
          title="My assignments"
          description="Applications currently assigned to you for inspection."
          badge={d ? <Badge tone="warning">{d.pending} pending</Badge> : undefined}
        />
      </div>
    </div>
  );
}
