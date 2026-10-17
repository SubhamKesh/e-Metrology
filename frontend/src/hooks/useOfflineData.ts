import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useOnlineStatus } from "@/hooks/useOfflineSync";
import { prefetchAssignments, restoreQueryCache, startQueryCachePersistence } from "@/lib/offlineCache";

/**
 * Keeps an officer's assignments available offline. Mount once (AppShell), officers only:
 *  - loads the copy saved on this device, so screens open instantly with no signal
 *  - saves the assignments to the device whenever they change
 *  - while online, downloads every assigned application + instrument (on open, when the
 *    connection returns, when the app comes back to the foreground, and every 5 minutes)
 */
export function useOfflineData(userId: string | undefined) {
  const qc = useQueryClient();
  const online = useOnlineStatus();

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    let stop = () => {};
    restoreQueryCache(qc, userId).finally(() => {
      if (!cancelled) stop = startQueryCachePersistence(qc, userId);
    });
    return () => {
      cancelled = true;
      stop();
    };
  }, [qc, userId]);

  useEffect(() => {
    if (!userId || !online) return;
    const run = () => {
      if (document.visibilityState === "visible") prefetchAssignments(qc).catch(() => {});
    };
    run();
    const t = setInterval(run, 5 * 60_000);
    document.addEventListener("visibilitychange", run);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", run);
    };
  }, [qc, userId, online]);
}
