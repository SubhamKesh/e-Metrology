import { useNavigate, useParams } from "react-router-dom";
import { useState } from "react";
import { ApplicationOverview } from "@/components/domain/ApplicationOverview";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";
import { useApplication, useClaimApplication } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import type { Role } from "@/lib/types";

export function OfficerApplicationDetail({ role }: { role: Extract<Role, "lmo" | "gatc"> }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { data: application, isLoading, isError, error, refetch } = useApplication(id);
  const claim = useClaimApplication();
  const [claimError, setClaimError] = useState<string | null>(null);

  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (isError || !application) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Application not found."} onRetry={refetch} />;
  }

  const isUnclaimed = application.status === "submitted" && !application.assigned_officer_id;
  const isMine = application.assigned_officer_id === user?.id;
  const canInspect = isMine && application.status === "scheduled";

  async function onClaim() {
    if (!id) return;
    setClaimError(null);
    try {
      await claim.mutateAsync(id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setClaimError("Someone else just claimed this application.");
        refetch();
      } else {
        setClaimError(err instanceof ApiError ? err.message : "Couldn't claim this application.");
      }
    }
  }

  return (
    <div>
      <ApplicationOverview
        application={application}
        actions={
          <div className="flex flex-col items-end gap-2">
            {isUnclaimed && (
              <Button onClick={onClaim} loading={claim.isPending}>
                Claim this application
              </Button>
            )}
            {canInspect && (
              <Button onClick={() => navigate(`/app/${role}/applications/${id}/inspect`)}>
                Start verification
              </Button>
            )}
            {isMine && application.status === "inspected" && (
              <p className="text-sm text-slate-400">Inspection submitted — awaiting certificate generation.</p>
            )}
          </div>
        }
      />
      {claimError && <p className="max-w-2xl text-sm text-danger">{claimError}</p>}
    </div>
  );
}
