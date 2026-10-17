import { useNavigate, useParams } from "react-router-dom";
import { useState } from "react";
import { ApplicationOverview } from "@/components/domain/ApplicationOverview";
import { SchedulePicker } from "@/components/domain/SchedulePicker";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";
import { useApplication, useClaimApplication, useRescheduleApplication } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useDrafts } from "@/hooks/useDrafts";
import type { Role, ScheduleInput } from "@/lib/types";

export function OfficerApplicationDetail({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { data: application, isLoading, isError, error, refetch } = useApplication(id);
  const claim = useClaimApplication();
  const reschedule = useRescheduleApplication();
  const [dialog, setDialog] = useState<"claim" | "reschedule" | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const hasDraft = useDrafts(user?.id).some((d) => d.application_id === id);

  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (isError || !application) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Application not found."} onRetry={refetch} />;
  }

  const isUnclaimed = application.status === "submitted" && !application.assigned_officer_id;
  const isMine = application.assigned_officer_id === user?.id;
  const canInspect = isMine && application.status === "scheduled";
  const canReschedule = isMine && application.status === "scheduled";

  function close() {
    setDialog(null);
    setFormError(null);
  }

  async function onSubmit(input: ScheduleInput) {
    if (!id || !dialog) return;
    setFormError(null);
    try {
      if (dialog === "claim") await claim.mutateAsync({ id, ...input });
      else await reschedule.mutateAsync({ id, ...input });
      close();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && dialog === "claim" && /claimed/i.test(err.message)) {
        close();
        setFormError("Someone else just claimed this application.");
        refetch();
        return;
      }
      // Slot-full and bad-date messages come from the server in plain language.
      setFormError(err instanceof ApiError ? err.message : "Couldn't save the schedule. Please try again.");
    }
  }

  return (
    <div>
      <ApplicationOverview
        application={application}
        scheduleActions={
          canReschedule ? (
            <Button size="sm" variant="secondary" onClick={() => setDialog("reschedule")}>
              Reschedule
            </Button>
          ) : undefined
        }
        actions={
          <div className="flex flex-col items-end gap-2">
            {isUnclaimed && <Button onClick={() => setDialog("claim")}>Claim and schedule</Button>}
            {canInspect && (
              <Button onClick={() => navigate(`/app/${role}/applications/${id}/inspect`)}>
                {hasDraft ? "Continue verification (draft)" : "Start verification"}
              </Button>
            )}
            {isMine && application.status === "inspected" && (
              <p className="text-sm text-slate-500">Inspection submitted — awaiting certificate generation.</p>
            )}
          </div>
        }
      />
      {formError && !dialog && <p className="max-w-2xl text-sm text-danger">{formError}</p>}

      <SchedulePicker
        open={dialog === "claim"}
        title="Claim and schedule inspection"
        description="Pick the date and slot you will inspect this instrument. The owner is emailed the booking."
        submitLabel="Claim and book"
        busy={claim.isPending}
        error={formError}
        onClose={close}
        onSubmit={onSubmit}
      />
      <SchedulePicker
        open={dialog === "reschedule"}
        title="Reschedule inspection"
        description="The owner is emailed the new date and slot."
        submitLabel="Reschedule"
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
