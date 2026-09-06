import { cn } from "@/lib/cn";
import type { ApplicationStatus } from "@/lib/types";
import { APPLICATION_STATUS_LABEL } from "@/components/ui/StatusBadge";

const HAPPY_PATH: ApplicationStatus[] = ["submitted", "scheduled", "inspected", "certified"];

// Rejection and expiry are terminal/side branches, not steps on the happy path —
// shown as a callout instead of forcing them into the linear stepper.
export function LifecycleTimeline({ current }: { current: ApplicationStatus }) {
  if (current === "rejected") {
    return (
      <div className="rounded-md border border-danger-50 bg-danger-50/50 px-4 py-3 text-sm text-danger">
        This application was rejected at inspection. See the inspection record for observations.
      </div>
    );
  }

  const effectiveIndex =
    current === "expiring" || current === "expired" ? HAPPY_PATH.length - 1 : HAPPY_PATH.indexOf(current);

  return (
    <div>
      <ol className="flex items-center">
        {HAPPY_PATH.map((step, i) => {
          const done = i < effectiveIndex;
          const isCurrent = i === effectiveIndex;
          return (
            <li key={step} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-2">
                <div
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium",
                    done && "border-teal bg-teal text-white",
                    isCurrent && "border-teal text-teal",
                    !done && !isCurrent && "border-line text-slate-400",
                  )}
                >
                  {done ? "✓" : i + 1}
                </div>
                <span
                  className={cn(
                    "whitespace-nowrap text-xs",
                    isCurrent ? "font-medium text-ink" : "text-slate-400",
                  )}
                >
                  {APPLICATION_STATUS_LABEL[step]}
                </span>
              </div>
              {i < HAPPY_PATH.length - 1 && (
                <div className={cn("mx-2 h-px flex-1", done ? "bg-teal" : "bg-line")} />
              )}
            </li>
          );
        })}
      </ol>
      {(current === "expiring" || current === "expired") && (
        <div
          className={cn(
            "mt-3 rounded-md px-4 py-2 text-sm",
            current === "expiring" ? "bg-warning-50 text-warning" : "bg-danger-50 text-danger",
          )}
        >
          {current === "expiring"
            ? "Certificate is within 30 days of expiry — renewal reminder sent."
            : "Certificate has expired. A re-verification application is required."}
        </div>
      )}
    </div>
  );
}
