// Device-local queue of inspections that couldn't be sent yet (no signal in the field).
//
// Stored in IndexedDB so it survives reloads and app restarts. Each entry holds the
// finished inspection plus any photos taken offline (as blobs, uploaded at sync time).
// Entries are tagged with the officer's user id and only ever synced for that officer.
// Nothing here is cached by the service worker; it lives only in this browser profile.

export interface QueuedInspection {
  client_id: string; // idempotency key, also the IndexedDB key
  user_id: string;
  application_id: string;
  label: string; // shown to the officer, e.g. "Weighing scale · Acme X100"
  observations: string;
  result: "pass" | "fail";
  photos: string[]; // already-uploaded photo URLs
  pending_photos: { name: string; type: string; blob: Blob }[]; // taken offline, still to upload
  identity_method: "qr" | "manual";
  location: { lat: number; lng: number; accuracy_m?: number };
  captured_at: string; // ISO time the officer pressed Submit
  status: "pending" | "failed";
  error?: string; // why it was rejected (status "failed")
  attempts: number;
}

const DB_NAME = "maapsetu-offline";
const STORE = "inspections";
const CHANGE_EVENT = "maapsetu:queue-changed";

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  const p = new Promise<IDBDatabase>((resolve, reject) => {
    if (typeof indexedDB === "undefined") return reject(new Error("IndexedDB unavailable"));
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE, { keyPath: "client_id" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  }).catch((e) => {
    dbPromise = null;
    throw e;
  });
  dbPromise = p;
  return p;
}

function run<T>(mode: "readonly" | "readwrite", fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const req = fn(tx.objectStore(STORE));
        tx.oncomplete = () => resolve(req.result);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      }),
  );
}

function notify() {
  window.dispatchEvent(new Event(CHANGE_EVENT));
  try {
    new BroadcastChannel(CHANGE_EVENT).postMessage(1); // other tabs
  } catch {
    // BroadcastChannel unsupported: other tabs pick changes up on their next poll
  }
}

export function onQueueChange(cb: () => void): () => void {
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

export async function enqueueInspection(item: Omit<QueuedInspection, "status" | "attempts">): Promise<void> {
  await run("readwrite", (s) => s.put({ ...item, status: "pending", attempts: 0 } satisfies QueuedInspection));
  notify();
}

export async function listQueued(userId: string): Promise<QueuedInspection[]> {
  const all = await run<QueuedInspection[]>("readonly", (s) => s.getAll());
  return all.filter((i) => i.user_id === userId).sort((a, b) => a.captured_at.localeCompare(b.captured_at));
}

export async function updateQueued(item: QueuedInspection): Promise<void> {
  await run("readwrite", (s) => s.put(item));
  notify();
}

export async function removeQueued(clientId: string): Promise<void> {
  await run("readwrite", (s) => s.delete(clientId));
  notify();
}