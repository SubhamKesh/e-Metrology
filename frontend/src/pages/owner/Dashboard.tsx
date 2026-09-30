import { ActionCard, DashboardHero, SectionTitle, StatCard } from "@/components/ui/Card";
import { ButtonLink } from "@/components/ui/Button";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { useDashboard } from "@/hooks/useData";
import type { OwnerDashboard } from "@/lib/types";
import { ROLE_LABEL } from "@/lib/types";
import { useAuth } from "@/context/AuthContext";

export default function OwnerDashboardPage() {
  const { user } = useAuth();
  const { data, isLoading, isError, refetch } = useDashboard("owner");
  const d = data as OwnerDashboard | undefined;

  return (
    <div>
      <DashboardHero
        roleLabel={ROLE_LABEL.owner}
        title={`Welcome back, ${user?.name.split(" ")[0] ?? ""}`}
        description="Here's where your instruments stand today."
        action={<ButtonLink to="/app/owner/instruments/new">Register instrument</ButtonLink>}
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
          <StatCard label="Total instruments" value={d.total_instruments} to="/app/owner/instruments" />
          <StatCard label="Verified" value={d.verified} tone="success" to="/app/owner/certificates" />
          <StatCard label="Pending" value={d.pending} tone="warning" to="/app/owner/applications" />
          <StatCard label="Expired" value={d.expired} tone="danger" to="/app/owner/certificates" />
        </div>
      ) : null}

      {d?.next_expiry && (
        <div
          role="status"
          className="mt-6 flex flex-col gap-1 rounded-xl border border-warning/30 bg-warning-50 p-4 sm:p-5"
        >
          <p className="text-sm font-semibold text-warning">Upcoming renewal</p>
          <p className="text-sm text-ink">
            {d.next_expiry.instrument_type} · Serial {d.next_expiry.uiid} expires on{" "}
            {new Date(d.next_expiry.valid_until).toLocaleDateString("en-IN", { dateStyle: "long" })} —{" "}
            {d.next_expiry.days_remaining} day{d.next_expiry.days_remaining === 1 ? "" : "s"} remaining.
          </p>
        </div>
      )}

      <SectionTitle>Quick actions</SectionTitle>
      <div className="grid gap-3 sm:grid-cols-3 sm:gap-4">
        <ActionCard to="/app/owner/instruments" title="View instruments" description="Review registered equipment and their current verification status." />
        <ActionCard to="/app/owner/applications/new" title="Submit application" description="Create a new verification request for an existing instrument." primary />
        <ActionCard to="/app/owner/certificates" title="Review certificates" description="Check issued certificates, validity windows, and renewal timing." />
      </div>
    </div>
  );
}
