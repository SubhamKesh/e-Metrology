import { buttonClasses } from "@/components/ui/Button";
import { useGeoDistricts, useGeoStates } from "@/hooks/useData";
import { downloadIcs, googleCalendarUrl, type CalendarEvent } from "@/lib/calendar";
import { slotLabel } from "@/lib/schedule";
import type { Application, Instrument } from "@/lib/types";

/** One-click Google Calendar link and a downloadable .ics file. No account linking. */
export function AddToCalendar({ application, instrument }: { application: Application; instrument?: Instrument }) {
  const loc = instrument?.location;
  const { data: states } = useGeoStates();
  const { data: districts } = useGeoDistricts(loc?.state_code);

  if (!application.scheduled_date || !application.slot) return null;

  const stateName = states?.find((s) => s.code === loc?.state_code)?.name ?? loc?.state_code;
  const districtName = districts?.find((d) => d.code === loc?.district_code)?.name ?? loc?.district_code;
  const location = loc ? [loc.address_line, districtName, stateName].filter(Boolean).join(", ") : undefined;
  const what = instrument ? `${instrument.type}${instrument.uiid ? ` (${instrument.uiid})` : ""}` : "instrument";

  const event: CalendarEvent = {
    uid: application.id,
    date: application.scheduled_date,
    slot: application.slot,
    // A reschedule adds a history entry, which makes calendars treat a re-imported file as newer.
    sequence: application.schedule_history?.length ?? 0,
    title: `Legal Metrology inspection: ${what}`,
    location,
    description: [
      `Slot: ${slotLabel(application.slot, application.slot_label)}`,
      "Keep the instrument accessible, with its serial number plate.",
      `Application: ${window.location.href}`,
    ].join("\n"),
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <a
        href={googleCalendarUrl(event)}
        target="_blank"
        rel="noopener noreferrer"
        className={buttonClasses("secondary", "sm")}
      >
        Add to Google Calendar
      </a>
      <button
        type="button"
        className={buttonClasses("secondary", "sm")}
        onClick={() => downloadIcs(event, `inspection-${application.id.slice(-6)}.ics`)}
      >
        Download .ics
      </button>
    </div>
  );
}
