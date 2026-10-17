import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { SelectInput, TextArea } from "@/components/ui/Field";
import { Skeleton } from "@/components/ui/States";
import { useSlotAvailability } from "@/hooks/useData";
import { ApiError } from "@/lib/api";
import { formatScheduleDate } from "@/lib/schedule";
import { cn } from "@/lib/cn";
import type { ScheduleInput, ScheduleSlot } from "@/lib/types";

interface Props {
  open: boolean;
  title: string;
  description?: string;
  submitLabel: string;
  /** Whose diary to show. Admins must pass the officer; officers leave it out (their own). */
  officerId?: string;
  /** The booking being changed, so the same slot can't be picked again. */
  current?: { date: string; slot: ScheduleSlot } | null;
  askReason?: boolean;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onSubmit: (input: ScheduleInput) => void;
}

export function SchedulePicker(props: Props) {
  // Mounted only while open, so every opening starts from a clean form.
  if (!props.open) return null;
  return <Picker {...props} />;
}

function Picker({ title, description, submitLabel, officerId, current, askReason, busy, error, onClose, onSubmit }: Props) {
  const { data, isLoading, isError, error: loadError, refetch } = useSlotAvailability(officerId);
  const [date, setDate] = useState("");
  const [slot, setSlot] = useState<ScheduleSlot | "">("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  // Only dates that can still take at least one inspection are offered.
  const days = useMemo(
    () => (data?.days ?? []).filter((d) => d.bookable && d.slots.some((s) => s.available > 0)),
    [data],
  );

  useEffect(() => {
    if (!date && days.length) setDate(days[0].date);
  }, [days, date]);

  const day = days.find((d) => d.date === date);
  const unchanged = !!current && current.date === date && current.slot === slot;
  const canSubmit = !!date && !!slot && !unchanged && !busy;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/45 p-4 sm:items-center" onClick={() => !busy && onClose()}>
      <div
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-line bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="schedule-title"
      >
        <h2 id="schedule-title" className="text-base font-semibold text-ink">
          {title}
        </h2>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}

        <div className="mt-4 flex flex-col gap-4">
          {isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : isError ? (
            <div className="text-sm text-danger">
              {loadError instanceof ApiError ? loadError.message : "Couldn't load available slots."}{" "}
              <button type="button" className="underline" onClick={() => refetch()}>
                Retry
              </button>
            </div>
          ) : days.length === 0 ? (
            <p className="text-sm text-slate-600">No free slots in the next {data?.days.length ?? 30} days.</p>
          ) : (
            <>
              <SelectInput
                label="Inspection date"
                value={date}
                onChange={(e) => {
                  setDate(e.target.value);
                  setSlot("");
                }}
                options={days.map((d) => ({ value: d.date, label: formatScheduleDate(d.date) }))}
                hint="Inspections are not held on Sundays."
              />

              <fieldset>
                <legend className="mb-1.5 text-sm font-medium text-ink">Time slot</legend>
                <div className="grid gap-2">
                  {(day?.slots ?? []).map((s) => {
                    const full = s.available <= 0;
                    const selected = slot === s.slot;
                    return (
                      <label
                        key={s.slot}
                        className={cn(
                          "flex cursor-pointer items-center justify-between gap-3 rounded-md border px-3 py-2.5 text-sm",
                          selected ? "border-teal bg-teal-50" : "border-line bg-white",
                          full && "cursor-not-allowed opacity-50",
                        )}
                      >
                        <span className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="slot"
                            value={s.slot}
                            checked={selected}
                            disabled={full}
                            onChange={() => setSlot(s.slot)}
                          />
                          {s.label}
                        </span>
                        <span className="text-xs text-slate-500">{full ? "Full" : `${s.available} of ${s.capacity} left`}</span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              {askReason && (
                <TextArea
                  label="Reason (optional)"
                  value={reason}
                  maxLength={300}
                  rows={2}
                  onChange={(e) => setReason(e.target.value)}
                  hint="Included in the email to the owner."
                />
              )}
            </>
          )}

          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            loading={busy}
            disabled={!canSubmit}
            onClick={() => slot && onSubmit({ date, slot, reason: reason.trim() || undefined })}
          >
            {submitLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
