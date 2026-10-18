import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { CasesApi } from "@/lib/endpoints";
import { useAuth } from "@/context/AuthContext";
import type { CaseRef } from "@/lib/types";
import { CaseStatusBadge, LevelBadge } from "./CaseBadges";

// One cell for the enforcement lists: shows the open case on an instrument, or lets an officer open one.
export function CaseCell({ instrumentId, caseRef }: { instrumentId: string; caseRef: CaseRef | null }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const base = `/app/${user?.role}/oversight/cases`;

  const open = useMutation({
    mutationFn: () => CasesApi.open(instrumentId),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["oversight"] });
      navigate(`${base}/${c.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Couldn't open the case."),
  });

  if (caseRef) {
    return (
      <div className="flex flex-col items-start gap-1.5">
        <div className="flex flex-wrap gap-1">
          <CaseStatusBadge status={caseRef.status} />
          <LevelBadge level={caseRef.level} />
        </div>
        <Button variant="secondary" size="sm" onClick={() => navigate(`${base}/${caseRef.id}`)}>
          View case
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-start gap-1.5">
      <Button variant="secondary" size="sm" loading={open.isPending} onClick={() => open.mutate()}>
        Open case
      </Button>
      {error && <p className="max-w-[14rem] text-xs text-danger">{error}</p>}
    </div>
  );
}
