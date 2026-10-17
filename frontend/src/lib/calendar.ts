// "Add to calendar" without any account linking: a Google Calendar link and a downloadable
// .ics file (opens in Outlook, Apple Calendar and Google Calendar). No OAuth, nothing stored.
import { slotWindow } from "./schedule";
import type { ScheduleSlot } from "./types";

export interface CalendarEvent {
  /** Application id; makes the event's UID stable so re-importing after a reschedule updates it. */
  uid: string;
  date: string;
  slot: ScheduleSlot;
  title: string;
  location?: string;
  description?: string;
  /** Bump on every reschedule so calendars treat the file as a newer version. */
  sequence?: number;
}

function utcStamp(d: Date): string {
  return d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z"); // 20261102T043000Z
}

export function googleCalendarUrl(ev: CalendarEvent): string {
  const { start, end } = slotWindow(ev.date, ev.slot);
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: ev.title,
    dates: `${utcStamp(start)}/${utcStamp(end)}`,
  });
  if (ev.location) params.set("location", ev.location);
  if (ev.description) params.set("details", ev.description);
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function escapeText(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

// RFC 5545: lines are at most 75 octets; continuation lines start with a space.
function fold(line: string): string {
  const enc = new TextEncoder();
  if (enc.encode(line).length <= 75) return line;
  const out: string[] = [];
  let cur = "";
  for (const ch of line) {
    const limit = out.length === 0 ? 75 : 74; // continuation lines carry a leading space
    if (enc.encode(cur + ch).length > limit) {
      out.push(cur);
      cur = ch;
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out.join("\r\n ");
}

export function buildIcs(ev: CalendarEvent): string {
  const { start, end } = slotWindow(ev.date, ev.slot);
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//MaapSetu//Inspection//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    `UID:${ev.uid}@maapsetu`,
    `DTSTAMP:${utcStamp(new Date())}`,
    `SEQUENCE:${ev.sequence ?? 0}`,
    `DTSTART:${utcStamp(start)}`,
    `DTEND:${utcStamp(end)}`,
    `SUMMARY:${escapeText(ev.title)}`,
  ];
  if (ev.location) lines.push(`LOCATION:${escapeText(ev.location)}`);
  if (ev.description) lines.push(`DESCRIPTION:${escapeText(ev.description)}`);
  lines.push(
    "BEGIN:VALARM",
    "ACTION:DISPLAY",
    "DESCRIPTION:Inspection reminder",
    "TRIGGER:-PT1H",
    "END:VALARM",
    "END:VEVENT",
    "END:VCALENDAR",
  );
  return lines.map(fold).join("\r\n") + "\r\n";
}

export function downloadIcs(ev: CalendarEvent, filename = "inspection.ics"): void {
  const blob = new Blob([buildIcs(ev)], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
