import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { listQueued, onQueueChange, removeQueued, type QueuedInspection } from "@/lib/offlineQueue";
import { syncQueue } from "@/lib/offlineSync";

export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  return online;
}

/** The signed-in officer's queued inspections, kept live. Read-only. */
export function useQueuedInspections(userId: string | undefined): QueuedInspection[] {
  const [items, setItems] = useState<QueuedInspection[]>([]);
  const refresh = useCallback(() => {
    if (!userId) return setItems([]);
    listQueued(userId).then(setItems, () => setItems([]));
  }, [userId]);
  useEffect(() => {
    refresh();
    return onQueueChange(refresh);
  }, [refresh]);
  return items;
}

/**
 * Sync engine. Mount it once (AppShell). Sends the queue when the app opens, when the
 * connection returns, when the tab regains focus, and every minute while anything waits.
 */
export function useOfflineSync(userId: string | undefined) {
  const qc = useQueryClient();
  const online = useOnlineStatus();
  const items = useQueuedInspections(userId);
  const [syncing, setSyncing] = useState(false);
  const waiting = items.filter((i) => i.status === "pending").length;

  const syncNow = useCallback(async () => {
    if (!userId) return;
    setSyncing(true);
    try {
      const r = await syncQueue(userId);
      if (r.sent > 0 || r.failed > 0) {
        qc.invalidateQueries({ queryKey: ["applications"] });
        qc.invalidateQueries({ queryKey: ["application"] });
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["certificates"] });
      }
    } catch {
      // IndexedDB trouble: nothing to send from here
    } finally {
      setSyncing(false);
    }
  }, [userId, qc]);

  useEffect(() => {
    if (online) syncNow();
  }, [online, syncNow]);

  useEffect(() => {
    if (!online || waiting === 0) return;
    const t = setInterval(syncNow, 60_000);
    const onVisible = () => document.visibilityState === "visible" && syncNow();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [online, waiting, syncNow]);

  const discard = useCallback((clientId: string) => removeQueued(clientId), []);

  return { items, online, syncing, syncNow, discard };
}
