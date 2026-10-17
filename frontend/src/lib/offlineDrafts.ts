// Drafts: an inspection the officer has started but not submitted.
//
// Everything typed or captured so far (identity check, photos, notes) is saved on this device
// as they go, online or offline, and restored when they come back to the same application,
// whether that's after a dropped signal, a closed app or a phone restart. A draft is per
// officer and per application, and is removed the moment the inspection is submitted or saved
// to the send queue. Like the send queue, drafts survive sign-out, so unfinished work is
// never lost; they expire after 14 days.

import { kvDelete, kvGet, kvList, kvSet } from "@/lib/offlineStore";
import type { IdentityMethod } from "@/lib/types";

export interface InspectionDraft {
  application_id: string;
  user_id: string;
  client_id: string; // kept so the eventual submission stays idempotent
  label: string; // shown in lists, e.g. "Weighing scale · Acme X100"
  entered_serial: string;
  identity_method: IdentityMethod;
  serial_confirmed: boolean;
  photos: string[]; // already uploaded
  pending_photos: { name: string; type: string; blob: Blob }[]; // taken offline, still to upload
  observations: string;
  // Detailed form. Readings are kept as typed (strings) so half-typed numbers survive a reload.
  readings?: { reference: string; indicated: string }[];
  checks?: Record<string, boolean>;
  seal_number?: string;
  updated_at: number; // ms since epoch
}

const PREFIX = "draft:";
const MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;
const CHANGE_EVENT = "maapsetu:drafts-changed";

const keyOf = (userId: string, applicationId: string) => `${PREFIX}${userId}:${applicationId}`;

function notify() {
  window.dispatchEvent(new Event(CHANGE_EVENT));
  try {
    new BroadcastChannel(CHANGE_EVENT).postMessage(1); // other tabs
  } catch {
    // BroadcastChannel unsupported: other tabs see changes on their next load
  }
}

export function onDraftsChange(cb: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, cb);
  let bc: BroadcastChannel | null = null;
  try {
    bc = new BroadcastChannel(CHANGE_EVENT);
    bc.onmessage = cb;
  } catch {
    bc = null;
  }
  return () => {
    window.removeEventListener(CHANGE_EVENT, cb);
    bc?.close();
  };
}

/** A form with nothing in it isn't worth keeping. */
export function isDraftEmpty(
  d: Pick<InspectionDraft, "observations" | "entered_serial" | "photos" | "pending_photos" | "readings" | "checks" | "seal_number">,
): boolean {
  return (
    d.observations.trim() === "" &&
    d.entered_serial === "" &&
    d.photos.length === 0 &&
    d.pending_photos.length === 0 &&
    !(d.readings ?? []).some((r) => r.reference.trim() !== "" || r.indicated.trim() !== "") &&
    Object.keys(d.checks ?? {}).length === 0 &&
    (d.seal_number ?? "").trim() === ""
  );
}

export async function saveDraft(d: InspectionDraft): Promise<void> {
  if (isDraftEmpty(d)) return deleteDraft(d.user_id, d.application_id);
  await kvSet(keyOf(d.user_id, d.application_id), { ...d, updated_at: Date.now() } satisfies InspectionDraft);
  notify();
}

export async function loadDraft(userId: string, applicationId: string): Promise<InspectionDraft | null> {
  const d = await kvGet<InspectionDraft>(keyOf(userId, applicationId));
  if (!d) return null;
  if (Date.now() - d.updated_at > MAX_AGE_MS) {
    await kvDelete(keyOf(userId, applicationId)).catch(() => {});
    return null;
  }
  return d;
}

export async function deleteDraft(userId: string, applicationId: string): Promise<void> {
  await kvDelete(keyOf(userId, applicationId));
  notify();
}

/** The officer's drafts, most recently edited first. */
export async function listDrafts(userId: string): Promise<InspectionDraft[]> {
  const all = await kvList<InspectionDraft>(`${PREFIX}${userId}:`);
  const cutoff = Date.now() - MAX_AGE_MS;
  return all.filter((d) => d.updated_at > cutoff).sort((a, b) => b.updated_at - a.updated_at);
}
