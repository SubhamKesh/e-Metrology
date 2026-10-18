import { useEffect, useMemo, useState } from "react";

/** A value that follows `value` after it has stopped changing for `delay` ms (so typing doesn't fire a request per key). */
export function useDebounced<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

type FilterValues = { q: string } & Record<string, string>;

export interface FilterController<T> {
  values: T;
  query: Partial<T>;
  dateError: string | null;
  active: boolean;
  set: <K extends keyof T>(key: K, value: T[K]) => void;
  clear: () => void;
}

/**
 * State for a search / filter bar.
 *  - `values`: what the controls show right now.
 *  - `query`: what to send to the server: the search text is debounced, empty filters are dropped, and a
 *    back-to-front date range is held back (with `dateError` to show) instead of being sent.
 */
export function useFilters<T extends FilterValues>(empty: T): FilterController<T> {
  const [values, setValues] = useState<T>(empty);
  const q = useDebounced(values.q.trim());

  const dateError =
    values.date_from && values.date_to && values.date_from > values.date_to
      ? "The 'from' date must not be after the 'to' date."
      : null;

  const query = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries({ ...values, q } as Record<string, string>)) {
      if (!value) continue;
      if (dateError && (key === "date_from" || key === "date_to")) continue;
      out[key] = value;
    }
    return out as Partial<T>;
  }, [values, q, dateError]);

  const active = Object.entries(values as Record<string, string>).some(
    ([key, value]) => value !== (empty as Record<string, string>)[key],
  );
  return {
    values,
    query,
    dateError,
    active,
    set: <K extends keyof T>(key: K, value: T[K]) => setValues((v) => ({ ...v, [key]: value })),
    clear: () => setValues(empty),
  };
}
