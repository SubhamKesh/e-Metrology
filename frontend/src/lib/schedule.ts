// Inspection slots. Mirrors backend/app/services/scheduling.py (SLOTS) — keep the two in step.
// All dates are India calendar dates ("YYYY-MM-DD"); IST has no daylight saving, so a fixed
// +05:30 offset is exact.
import type { ScheduleSlot } from "./types";

export const SLOT_INFO: Record<ScheduleSlot, { label: string; start: [number, number]; end: [number, number] }> = {
  morning: { label: "Morning (10:00 AM - 1:00 PM)", start: [10, 0], end: [13, 0] },
  afternoon: { label: "Afternoon (2:00 PM - 5:00 PM)", start: [14, 0], end: [17, 0] },
};

const IST_OFFSET_MIN = 5 * 60 + 30;

/** "Mon, 2 Nov 2026" for a YYYY-MM-DD string (rendered in UTC so the viewer's timezone can't shift it). */
export function formatScheduleDate(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  if (!y || !m || !d) return date;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function slotLabel(slot?: ScheduleSlot | null, fallback?: string | null): string {
  return (slot && SLOT_INFO[slot]?.label) || fallback || "";
}

/** Start and end of a booked slot as real instants. */
export function slotWindow(date: string, slot: ScheduleSlot): { start: Date; end: Date } {
  const [y, m, d] = date.split("-").map(Number);
  const { start, end } = SLOT_INFO[slot];
  const at = ([h, min]: [number, number]) => new Date(Date.UTC(y, m - 1, d, h, min) - IST_OFFSET_MIN * 60_000);
  return { start: at(start), end: at(end) };
}
