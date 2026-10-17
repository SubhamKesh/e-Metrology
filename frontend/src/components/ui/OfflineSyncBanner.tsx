import { useAuth } from "@/context/AuthContext";
import { useOfflineSync } from "@/hooks/useOfflineSync";

/** Officer-only status strip: offline notice, inspections waiting to send, and any the server rejected. */
export function OfflineSyncBanner() {
  const { user } = useAuth();
  const { items, online, syncing, syncNow, discard, syncError } = useOfflineSync(user?.id);
  const waiting = items.filter((i) => i.status === "pending");
  const failed = items.filter((i) => i.status === "failed");
  if (online && waiting.length === 0 && failed.length === 0) return null;

  return (
    <div role="status" aria-live="polite" className="mb-4 flex flex-col gap-2">
      {!online && (
        <div className="rounded-lg border border-line bg-paper2/60 px-4 py-3 text-sm text-ink">
          You're offline. Inspections you submit are saved on this device and sent automatically when you're back online.
        </div>
      )}
      {waiting.length > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-line bg-white px-4 py-3 text-sm shadow-sm">
          <p className="text-ink">
            {syncing
              ? "Sending saved inspections…"
              : `${waiting.length} inspection${waiting.length > 1 ? "s" : ""} saved on this device, waiting to send.`}
          </p>
          {online && !syncing && (
            <button
              type="button"
              onClick={syncNow}
              className="shrink-0 rounded-md bg-teal px-3 py-1.5 font-medium text-white hover:bg-teal-600"
            >
              Send now
            </button>
          )}
        </div>
      )}
      {waiting.length > 0 && !syncing && (syncError ?? waiting[0]?.last_error) && (
        <div className="rounded-lg border border-danger/30 bg-danger-50 px-4 py-3 text-sm text-ink">
          {syncError ?? waiting[0]?.last_error}
        </div>
      )}
      {failed.map((i) => (
        <div key={i.client_id} className="rounded-lg border border-danger/30 bg-danger-50 px-4 py-3 text-sm">
          <p className="font-medium text-danger">Couldn't send: {i.label}</p>
          <p className="mt-1 text-ink">{i.error ?? "The server rejected this inspection."}</p>
          <button type="button" onClick={() => discard(i.client_id)} className="mt-2 font-medium text-danger underline">
            Discard saved inspection
          </button>
        </div>
      ))}
    </div>
  );
}
