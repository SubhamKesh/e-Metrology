import { useCallback, useEffect, useState } from "react";
import { listDrafts, onDraftsChange, type InspectionDraft } from "@/lib/offlineDrafts";

/** The signed-in officer's unfinished inspections, kept live. */
export function useDrafts(userId: string | undefined): InspectionDraft[] {
  const [drafts, setDrafts] = useState<InspectionDraft[]>([]);
  const refresh = useCallback(() => {
    if (!userId) return setDrafts([]);
    listDrafts(userId).then(setDrafts, () => setDrafts([]));
  }, [userId]);
  useEffect(() => {
    refresh();
    return onDraftsChange(refresh);
  }, [refresh]);
  return drafts;
}
