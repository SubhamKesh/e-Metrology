// Tiny key-value store on IndexedDB for data the app keeps for offline use (the officer's cached
// assignments and last signed-in profile). Separate database from the inspection queue so the
// queue's schema never has to change. Everything here is wiped on sign-out (see offlineCache.ts).

const DB_NAME = "maapsetu-cache";
const STORE = "kv";

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  const p = new Promise<IDBDatabase>((resolve, reject) => {
    if (typeof indexedDB === "undefined") return reject(new Error("IndexedDB unavailable"));
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
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

export async function kvGet<T>(key: string): Promise<T | undefined> {
  return (await run<T | undefined>("readonly", (s) => s.get(key))) ?? undefined;
}

export async function kvSet(key: string, value: unknown): Promise<void> {
  await run("readwrite", (s) => s.put(value, key));
}

export async function kvDelete(key: string): Promise<void> {
  await run("readwrite", (s) => s.delete(key));
}

/** Every value whose key starts with `prefix`. */
export async function kvList<T>(prefix: string): Promise<T[]> {
  return run<T[]>("readonly", (s) => s.getAll(IDBKeyRange.bound(prefix, prefix + "\uffff")));
}
