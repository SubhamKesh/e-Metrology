import { ApiError } from "@/lib/api";
import { InspectionApi, UploadApi } from "@/lib/endpoints";
import { compressImage } from "@/lib/imageCompress";
import { listQueued, removeQueued, updateQueued, type QueuedInspection } from "@/lib/offlineQueue";

export interface SyncResult {
  sent: number; // inspections the server accepted
  failed: number; // inspections the server rejected (kept for the officer to review)
  remaining: number; // still waiting (offline, server busy, signed out)
  error?: string; // plain-words reason the last attempt stopped early, for the officer
}

let running = false;

/** Why a rejected inspection won't ever succeed by retrying, in plain words. */
function rejectionReason(err: ApiError): string {
  if (err.status === 403) return "This application is no longer assigned to you.";
  if (err.status === 404) return "This application no longer exists.";
  if (err.status === 409) return "This application was already inspected or is no longer scheduled.";
  if (err.status === 413) return "A photo is too large for the server. Discard this and resubmit with smaller photos.";
  return err.message;
}

/** Plain-words reason for a failure that will be retried later. */
function retryReason(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return "Can't reach the server right now. Will retry automatically.";
    if (err.status === 401) return "Your session expired. Sign in again and it will send.";
    if (err.status === 408 || err.status === 429) return "Server is busy. Will retry shortly.";
    if (err.status >= 500) return `Server error (${err.status}). Will retry automatically.`;
    return err.message;
  }
  return err instanceof Error ? `Couldn't send: ${err.message}` : "Couldn't send. Will retry automatically.";
}

// Progress holder so a failure halfway through photo uploads keeps the photos that already went up.
async function sendOne(state: { current: QueuedInspection }): Promise<void> {
  while (state.current.pending_photos.length > 0) {
    const [next, ...rest] = state.current.pending_photos;
    const raw = new File([next.blob], next.name, { type: next.type });
    const file = await compressImage(raw);
    const { url } = await UploadApi.photo(file);
    state.current = { ...state.current, photos: [...state.current.photos, url], pending_photos: rest };
    await updateQueued(state.current);
  }
  const c = state.current;
  await InspectionApi.create({
    application_id: c.application_id,
    observations: c.observations,
    result: c.result,
    photos: c.photos,
    identity_method: c.identity_method,
    location: c.location,
    client_id: c.client_id,
    captured_at: c.captured_at,
  });
}

/**
 * Sends the officer's queued inspections, oldest first. Safe to call at any time and from
 * several places: only one run happens at once, and the server ignores a repeated client_id.
 *  - network / server trouble  -> stop, keep everything, remember why, try again later
 *  - signed out (401)          -> stop, keep everything for after sign-in
 *  - server says no (4xx)      -> mark that one "failed" with a reason and carry on
 */
export async function syncQueue(userId: string): Promise<SyncResult> {
  const result: SyncResult = { sent: 0, failed: 0, remaining: 0 };
  if (running) return result;
  running = true;
  try {
    const items = (await listQueued(userId)).filter((i) => i.status === "pending");
    for (let idx = 0; idx < items.length; idx++) {
      const state = { current: items[idx] };
      try {
        await sendOne(state);
        await removeQueued(state.current.client_id);
        result.sent += 1;
      } catch (err) {
        if (err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 401 && err.status !== 408 && err.status !== 429) {
          await updateQueued({ ...state.current, status: "failed", error: rejectionReason(err), attempts: state.current.attempts + 1 });
          result.failed += 1;
          continue;
        }
        const reason = retryReason(err);
        await updateQueued({ ...state.current, attempts: state.current.attempts + 1, last_error: reason }).catch(() => {});
        result.remaining = items.length - idx;
        result.error = reason;
        break;
      }
    }
  } finally {
    running = false;
  }
  return result;
}
