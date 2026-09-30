import { useLocation } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { useAuth } from "@/context/AuthContext";
import { ButtonLink } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { cn } from "@/lib/cn";

export interface PendingRouteState {
  email?: string;
  status?: "pending" | "rejected";
}

type StepState = "done" | "current" | "todo";

const STEPS: { title: string; body: string }[] = [
  { title: "Account created", body: "Your details have been received." },
  { title: "Administrator review", body: "An administrator checks and approves officer accounts." },
  { title: "Approved — sign in", body: "You'll be able to sign in as soon as you're approved." },
];

export default function PendingApproval() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const routeState = (location.state ?? {}) as PendingRouteState;
  const rejected = routeState.status === "rejected" || user?.status === "rejected";
  const email = routeState.email ?? user?.email;
  const name = user?.name;

  if (rejected) {
    return (
      <AuthLayout title="Registration not approved" subtitle="An administrator has declined this account.">
        <div className="rounded-xl border border-danger/20 bg-danger-50 p-4 text-sm text-ink" role="status">
          <p>
            {name ? `${name}, your` : "Your"} registration{email ? ` for ${email}` : ""} was not approved, so this
            account can't be used to sign in.
          </p>
          <p className="mt-2 text-slate-600">
            If you think this is a mistake, contact the department using the email address you registered with.
          </p>
        </div>
        <Actions onLeave={logout} />
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Account pending approval" subtitle="Your account is awaiting admin approval.">
      <div className="rounded-xl border border-warning/30 bg-warning-50 p-4 text-sm text-ink" role="status">
        <p>
          Thanks for registering{name ? `, ${name}` : ""}. An administrator must approve officer accounts before they
          can sign in.
        </p>
        {email && (
          <p className="mt-2 text-slate-600">
            Registered email: <span className="break-all font-medium text-ink">{email}</span>
          </p>
        )}
      </div>

      <ol className="mt-6 space-y-0" aria-label="Approval progress">
        {STEPS.map((s, i) => {
          const state: StepState = i === 0 ? "done" : i === 1 ? "current" : "todo";
          return (
            <li key={s.title} className="relative flex gap-3 pb-5 last:pb-0">
              {i < STEPS.length - 1 && (
                <span className="absolute left-[0.95rem] top-8 h-[calc(100%-1.5rem)] w-px bg-line" aria-hidden="true" />
              )}
              <span
                className={cn(
                  "z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm font-medium",
                  state === "done" && "border-teal bg-teal text-white",
                  state === "current" && "border-warning bg-warning-50 text-warning",
                  state === "todo" && "border-line bg-white text-slate-500",
                )}
                aria-hidden="true"
              >
                {state === "done" ? <Icon name="check" className="h-4 w-4" /> : i + 1}
              </span>
              <div className="min-w-0 pt-0.5">
                <p className="text-sm font-medium text-ink">
                  {s.title}
                  {state === "current" && <span className="ml-2 text-xs font-normal text-warning">In progress</span>}
                </p>
                <p className="text-sm text-slate-600">{s.body}</p>
              </div>
            </li>
          );
        })}
      </ol>

      <p className="mt-6 text-sm text-slate-600">
        You'll receive an email when your account is approved. If you need help, contact the department using your
        registered email.
      </p>
      <Actions onLeave={logout} />
    </AuthLayout>
  );
}

function Actions({ onLeave }: { onLeave: () => void }) {
  return (
    <div className="mt-6 flex flex-col gap-3 sm:flex-row">
      <ButtonLink to="/login" onClick={onLeave} className="w-full sm:w-auto">
        Back to sign in
      </ButtonLink>
      <ButtonLink to="/verify" variant="secondary" className="w-full sm:w-auto">
        Verify a certificate
      </ButtonLink>
    </div>
  );
}
