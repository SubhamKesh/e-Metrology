import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ApplicationOverview } from "@/components/domain/ApplicationOverview";
import { SchedulePicker } from "@/components/domain/SchedulePicker";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";
import { SelectInput } from "@/components/ui/Field";
import { useApplication, useAssignApplication, useRescheduleApplication } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import { AdminUsersApi } from "@/lib/endpoints";
import type { Application, ScheduleInput, User } from "@/lib/types";

// Mirrors the server's jurisdiction rule: an LMO covers one district, GATC the whole state.
function covers(officer: User, app: Application): boolean {
  const j = officer.jurisdiction;
  if (!j || !app.state_code || j.state_code !== app.state_code) return false;
  if (officer.role === "lmo") return !!j.district_code && j.district_code === app.district_code;
  return !j.district_code || j.district_code === app.district_code;
}

export default function AdminApplicationDetail() {
  const { id } = useParams();
  const { data: application, isLoading, isError, error, refetch } = useApplication(id);
  const { data: officers } = useQuery<User[]>({ queryKey: ["admin", "officers"], queryFn: () => AdminUsersApi.listOfficers() });
  const assign = useAssignApplication();
  const reschedule = useRescheduleApplication();
  const [dialog, setDialog] = useState<"pick" | "assign" | "reschedule" | null>(null);
  const [officerId, setOfficerId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const eligible = useMemo(
    () => (application && officers ? officers.filter((o) => o.status === "active" && covers(o, application)) : []),
    [officers, application],
  );

  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (isError || !application) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Application not found."} onRetry={refetch} />;
  }

  const open = application.status === "submitted" || application.status === "scheduled";
  const isScheduled = application.status === "scheduled";
  const options = eligible.map((o) => ({ value: o.id, label: `${o.name} (${o.role.toUpperCase()})` }));

  function close() {
    setDialog(null);
    setFormError(null);
  }

  async function onSubmit(input: ScheduleInput) {
    if (!id) return;
    setFormError(null);
    try {
      if (dialog === "assign") await assign.mutateAsync({ id, officer_id: officerId, ...input });
      else await reschedule.mutateAsync({ id, ...input });
      close();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Couldn't save the schedule. Please try again.");
    }
  }

  return (
    <div>
      <ApplicationOverview
        application={application}
        actions={
          open ? (
            <Button
              size="sm"
              onClick={() => {
                setOfficerId(application.assigned_officer_id ?? "");
                setDialog("pick");
              }}
            >
              {isScheduled ? "Reassign officer" : "Assign officer"}
            </Button>
          ) : undefined
        }
        scheduleActions={
          isScheduled ? (
            <Button size="sm" variant="secondary" onClick={() => setDialog("reschedule")}>
              Reschedule
            </Button>
          ) : undefined
        }
      />

      {dialog === "pick" && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/45 p-4 sm:items-center" onClick={close}>
          <div
            className="w-full max-w-md rounded-xl border border-line bg-white p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="pick-officer-title"
          >
            <h2 id="pick-officer-title" className="text-base font-semibold text-ink">
              {isScheduled ? "Reassign to another officer" : "Assign an officer"}
            </h2>
            <p className="mt-1 mb-4 text-sm text-slate-500">
              Only active officers whose jurisdiction covers this application are listed.
            </p>
            {options.length === 0 ? (
              <p className="text-sm text-slate-600">No active officer covers this application's district.</p>
            ) : (
              <SelectInput
                label="Officer"
                value={officerId}
                placeholder="Choose an officer"
                onChange={(e) => setOfficerId(e.target.value)}
                options={options}
              />
            )}
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={close}>
                Cancel
              </Button>
              <Button disabled={!officerId} onClick={() => setDialog("assign")}>
                Next: pick a slot
              </Button>
            </div>
          </div>
        </div>
      )}

      <SchedulePicker
        open={dialog === "assign"}
        title="Book the inspection"
        description="Slots shown are this officer's free places. Both the owner and the officer are emailed."
        submitLabel={isScheduled ? "Reassign and book" : "Assign and book"}
        officerId={officerId}
        askReason
        busy={assign.isPending}
        error={formError}
        onClose={close}
        onSubmit={onSubmit}
      />
      <SchedulePicker
        open={dialog === "reschedule"}
        title="Reschedule inspection"
        description="The owner is emailed the new date and slot."
        submitLabel="Reschedule"
        officerId={application.assigned_officer_id ?? undefined}
        current={
          application.scheduled_date && application.slot ? { date: application.scheduled_date, slot: application.slot } : null
        }
        askReason
        busy={reschedule.isPending}
        error={formError}
        onClose={close}
        onSubmit={onSubmit}
      />
    </div>
  );
}
