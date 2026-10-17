// Offline data for field officers (LMO / GATC only).
//
// Two things are kept on the officer's device so the app still works after being closed and
// reopened with no signal:
//   1. the last signed-in profile, so the app can open without being able to call /auth/me
//   2. the officer's own assignments (list, each application, each instrument, dashboard)
//
// Both are removed on sign-out, and both expire after OFFLINE_MAX_AGE_MS. Nothing here is ever
// kept for owners or admins. The unsent-inspection queue (offlineQueue.ts) is separate and is
// deliberately NOT wiped on sign-out, so an officer can never lose a finished inspection.

import { dehydrate, hydrate, type DehydratedState, type QueryClient, type QueryKey } from "@tanstack/react-query";
import { ApplicationApi, InstrumentApi } from "@/lib/endpoints";
import { kvDelete, kvGet, kvSet } from "@/lib/offlineStore";
import type { User } from "@/lib/types";

const USER_KEY = "offline-user";
const CACHE_KEY = "query-cache";
const OFFLINE_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000; // an offline-only session lasts at most a week
const MAX_QUERIES = 150;
const SAVE_DEBOUNCE_MS = 1500;

const isOfficer = (u: Pick<User, "role">) => u.role === "lmo" || u.role === "gatc";

// ---- last signed-in officer -------------------------------------------------------------------

interface StoredUser {
  user: User;
  saved_at: number;
}

export async function saveOfflineUser(user: User): Promise<void> {
  if (!isOfficer(user)) return;
  await kvSet(USER_KEY, { user, saved_at: Date.now() } satisfies StoredUser);
}

/** The officer who last signed in on this device, if their offline window hasn't run out. */
export async function loadOfflineUser(): Promise<User | null> {
  const stored = await kvGet<StoredUser>(USER_KEY);
  if (!stored || !isOfficer(stored.user)) return null;
  if (Date.now() - stored.saved_at > OFFLINE_MAX_AGE_MS) {
    await kvDelete(USER_KEY).catch(() => {});
    return null;
  }
  return stored.user;
}

/** Wipes everything kept for offline use (not the unsent-inspection queue). Call on sign-out. */
export async function clearOfflineData(): Promise<void> {
  await Promise.allSettled([kvDelete(USER_KEY), kvDelete(CACHE_KEY)]);
}

// ---- cached assignments -----------------------------------------------------------------------

interface PersistedCache {
  user_id: string;
  saved_at: number;
  state: DehydratedState;
}

// Only what an officer needs to open and complete an inspection offline.
function shouldPersist(key: QueryKey): boolean {
  const [name, arg] = key as [string, unknown];
  if (name === "application" || name === "instrument") return true;
  if (name === "dashboard") return arg === "lmo" || arg === "gatc";
  if (name === "applications") return typeof arg === "object" && arg !== null && (arg as { mine?: boolean }).mine === true;
  return false;
}

/** Loads the saved assignments into the in-memory cache. Fresh data from the server always wins. */
export async function restoreQueryCache(qc: QueryClient, userId: string): Promise<void> {
  try {
    const stored = await kvGet<PersistedCache>(CACHE_KEY);
    if (!stored) return;
    if (stored.user_id !== userId || Date.now() - stored.saved_at > OFFLINE_MAX_AGE_MS) {
      await kvDelete(CACHE_KEY);
      return;
    }
    hydrate(qc, stored.state);
  } catch {
    // storage trouble: the app just starts with an empty cache
  }
}

async function persistNow(qc: QueryClient, userId: string): Promise<void> {
  const fresh = dehydrate(qc, {
    shouldDehydrateQuery: (q) => q.state.status === "success" && shouldPersist(q.queryKey),
  });
  if (fresh.queries.length === 0) return;

  // Merge with what's already saved instead of replacing it: queries the app has let go of
  // from memory (garbage-collected) must not vanish from the offline copy.
  const stored = await kvGet<PersistedCache>(CACHE_KEY).catch(() => undefined);
  const previous = stored && stored.user_id === userId ? stored.state.queries : [];
  const merged = new Map(previous.map((q) => [q.queryHash, q]));
  for (const q of fresh.queries) {
    const old = merged.get(q.queryHash);
    if (!old || q.state.dataUpdatedAt >= old.state.dataUpdatedAt) merged.set(q.queryHash, q);
  }
  const cutoff = Date.now() - OFFLINE_MAX_AGE_MS;
  const queries = [...merged.values()]
    .filter((q) => q.state.dataUpdatedAt > cutoff)
    .sort((a, b) => b.state.dataUpdatedAt - a.state.dataUpdatedAt)
    .slice(0, MAX_QUERIES);

  await kvSet(CACHE_KEY, { user_id: userId, saved_at: Date.now(), state: { mutations: [], queries } } satisfies PersistedCache);
}

/** Saves the assignments to the device whenever they change. Returns a function that stops it. */
export function startQueryCachePersistence(qc: QueryClient, userId: string): () => void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const unsubscribe = qc.getQueryCache().subscribe(() => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      persistNow(qc, userId).catch(() => {});
    }, SAVE_DEBOUNCE_MS);
  });
  return () => {
    unsubscribe();
    if (timer) clearTimeout(timer);
  };
}

/**
 * Downloads everything the officer needs to work offline: their assignment list, plus each
 * assigned application and its instrument. Run while online; the persistence above then
 * saves the results to the device.
 */
export async function prefetchAssignments(qc: QueryClient): Promise<void> {
  const list = await qc.fetchQuery({
    queryKey: ["applications", { mine: true, status: undefined }],
    queryFn: () => ApplicationApi.list({ mine: true }),
    staleTime: 30_000,
  });
  // Applications waiting for an inspection first; cap so a big backlog can't flood the phone.
  const todo = [...list].sort((a, b) => Number(b.status === "scheduled") - Number(a.status === "scheduled")).slice(0, 25);
  const instrumentIds = new Set(todo.map((a) => a.instrument_id));
  await Promise.allSettled([
    ...todo.map((a) =>
      qc.prefetchQuery({ queryKey: ["application", a.id], queryFn: () => ApplicationApi.get(a.id), staleTime: 30_000 }),
    ),
    ...[...instrumentIds].map((id) =>
      qc.prefetchQuery({ queryKey: ["instrument", id], queryFn: () => InstrumentApi.get(id), staleTime: 30_000 }),
    ),
  ]);
}
