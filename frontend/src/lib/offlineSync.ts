import { ApiError } from "@/lib/api";
import { InspectionApi, UploadApi } from "@/lib/endpoints";
import { listQueued, removeQueued, updateQueued, type QueuedInspection } from "@/lib/offlineQueue";

export interface SyncResult {
  sent: number; // inspections the server accepted
  failed: number; // inspections the server rejected (kept for the officer to review)
  remaining: number; // still waiting (offline, server busy, signed out)
}

let running = false;

/** Why a rejected inspection won't ever succeed by retrying, in plain words. */
function rejectionReason(err: ApiError): string {
  if (err.status === 403) return "This application is no longer assigned to you.";
  if (err.status === 404) return "This application no longer exists.";
  if (err.status === 409) return "This application was already inspected or is no longer scheduled.";
  return err.message;
}

async function sendOne(item: QueuedInspection): Promise<void> {
  // Upload photos taken offline first. Each success is saved straight away so a
  // dropped connection halfway through doesn't re-upload what already went up.
  let current = item;
  while (current.pending_photos.length > 0) {
    const [next, ...rest] = current.pending_photos;
    const file = new File([next.blob], next.name, { type: next.type });
    const { url } = await UploadApi.photo(file);
    current = { ...current, photos: [...current.photos, url], pending_photos: rest };
    await updateQueued(current);
  }
  await InspectionApi.create({
    application_id: current.application_id,
    observations: current.observations,
    result: current.result,
    photos: current.photos,
    identity_method: current.identity_method,
    location: current.location,
    client_id: current.client_id,
    captured_at: current.captured_at,
  });
}

/**
 * Sends the officer's queued inspections, oldest first. Safe to call at any time and from
 * several places: only one run happens at once, and the server ignores a repeated client_id.
 *  - network / server trouble  -> stop, keep everything, try again later
 *  - signed out (401)          -> stop, keep everything for after sign-in
 *  - server says no (4xx)      -> mark that one "failed" with a reason and carry on
 */
export async function syncQueue(userId: string): Promise<SyncResult> {
  const result: SyncResult = { sent: 0, failed: 0, remaining: 0 };
  if (running || !navigator.onLine) return result;
  running = true;
  try {
    const items = (await listQueued(userId)).filter((i) => i.status === "pending");
    for (let idx = 0; idx < items.length; idx++) {
      const item = items[idx];
      try {
        await sendOne(item);
        await removeQueued(item.client_id);
        result.sent += 1;
      } catch (err) {
        if (err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 401 && err.status !== 408 && err.status !== 429) {
          await updateQueued({ ...item, status: "failed", error: rejectionReason(err), attempts: item.attempts + 1 });
          result.failed += 1;
          continue;
        }
        await updateQueued({ ...item, attempts: item.attempts + 1 }).catch(() => {});
        result.remaining = items.length - idx;
        break;
      }
    }
  } finally {
    running = false;
  }
  return result;
}
