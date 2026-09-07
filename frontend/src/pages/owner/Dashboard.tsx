import { Link } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { StatCard } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";
import { useDashboard } from "@/hooks/useData";
import type { OwnerDashboard } from "@/lib/types";
import { useAuth } from "@/context/AuthContext";

export default function OwnerDashboardPage() {
  const { user } = useAuth();
  const { data, isLoading, isError } = useDashboard("owner");
  const d = data as OwnerDashboard | undefined;

  return (
    <div>
      <PageHeader
        title={`Welcome back, ${user?.name.split(" ")[0]}`}
        description="Here's where your instruments stand today."
        action={
          <Link to="/app/owner/instruments/new">
            <Button>Register instrument</Button>
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
          <StatCard label="Total instruments" value={d.total_instruments} />
          <StatCard label="Verified" value={d.verified} tone="success" />
          <StatCard label="Pending" value={d.pending} tone="warning" />
          <StatCard label="Expired" value={d.expired} tone="danger" />
        </div>
      ) : null}

      {d?.next_expiry && (
        <div className="mt-6 rounded-lg border border-warning-50 bg-warning-50/50 p-5">
          <p className="text-sm font-medium text-warning">Upcoming renewal</p>
          <p className="mt-1 text-sm text-ink">
            {d.next_expiry.instrument_type} · Serial {d.next_expiry.uiid} expires on{" "}
            {new Date(d.next_expiry.valid_until).toLocaleDateString("en-IN", { dateStyle: "long" })} —{" "}
            {d.next_expiry.days_remaining} day{d.next_expiry.days_remaining === 1 ? "" : "s"} remaining.
          </p>
        </div>
      )}

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <QuickAction to="/app/owner/instruments/new" title="Register instrument" description="Add a new weighing or measuring instrument." />
        <QuickAction to="/app/owner/applications/new" title="Apply for verification" description="Submit an existing instrument for verification." />
        <QuickAction to="/app/owner/certificates" title="View certificates" description="See all issued certificates and their validity." />
      </div>
    </div>
  );
}

function QuickAction({ to, title, description }: { to: string; title: string; description: string }) {
  return (
    <Link
      to={to}
      className="rounded-lg border border-line bg-white p-5 shadow-panel transition-shadow hover:shadow-raised"
    >
      <p className="font-medium text-ink">{title}</p>
      <p className="mt-1 text-sm text-slate-500">{description}</p>
    </Link>
  );
}
