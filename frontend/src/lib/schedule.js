export const SLOT_INFO = {
    morning: { label: "Morning (10:00 AM - 1:00 PM)", start: [10, 0], end: [13, 0] },
    afternoon: { label: "Afternoon (2:00 PM - 5:00 PM)", start: [14, 0], end: [17, 0] },
};
const IST_OFFSET_MIN = 5 * 60 + 30;
/** "Mon, 2 Nov 2026" for a YYYY-MM-DD string (rendered in UTC so the viewer's timezone can't shift it). */
export function formatScheduleDate(date) {
    const [y, m, d] = date.split("-").map(Number);
    if (!y || !m || !d)
        return date;
    return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-IN", {
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
    });
}
export function slotLabel(slot, fallback) {
    return (slot && SLOT_INFO[slot]?.label) || fallback || "";
}
/** Start and end of a booked slot as real instants. */
export function slotWindow(date, slot) {
    const [y, m, d] = date.split("-").map(Number);
    const { start, end } = SLOT_INFO[slot];
    const at = ([h, min]) => new Date(Date.UTC(y, m - 1, d, h, min) - IST_OFFSET_MIN * 60000);
    return { start: at(start), end: at(end) };
}
