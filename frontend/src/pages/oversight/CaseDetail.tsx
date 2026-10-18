import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/Field";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { Badge } from "@/components/ui/StatusBadge";
import { CaseStatusBadge, KIND_LABEL, LEVEL_LABEL, LevelBadge, RESOLUTION_LABEL } from "@/components/domain/CaseBadges";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api";
import { CasesApi } from "@/lib/endpoints";
import type { CaseDetail, CaseEvent, CaseLevel } from "@/lib/types";

type Mode = "notice" | "note" | "escalate" | "close";

const NEXT_LEVEL: Record<CaseLevel, CaseLevel | null> = { lmo: "gatc", gatc: "admin", admin: null };

const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });
const dateOnly = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium" });

const FORM: Record<Mode, { title: string; label: string; hint?: string; required: boolean; confirm: string; danger?: boolean }> = {
  notice: {
    title: "Send a notice to the owner",
    label: "Message to the owner (optional)",
    hint: "The owner gets the standard notice by email and sees it in the app. Your message is added to it.",
    required: false,
    confirm: "Send notice",
  },
  note: {
    title: "Add a note",
    label: "Note",
    hint: "Only officers can see notes. The owner never does.",
    required: true,
    confirm: "Add note",
  },
  escalate: {
    title: "Escalate this case",
    label: "Reason (optional)",
    hint: "The case moves up one level and the officers there take over.",
    required: false,
    confirm: "Escalate",
  },
  close: {
    title: "Close this case",
    label: "Reason for closing",
    hint: "For example: the instrument was scrapped, or the owner has been dealt with in person.",
    required: true,
    confirm: "Close case",
    danger: true,
  },
};

// One enforcement case: the facts, the timeline, and the things an officer can do about it.
export default function CaseDetailPage() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const key = ["oversight", "case", id];

  const { data, isLoading, isError, error: loadError, refetch } = useQuery({ queryKey: key, queryFn: () => CasesApi.get(id) });

  const act = useMutation({
    mutationFn: ({ m, value }: { m: Mode; value: string }) => {
      if (m === "notice") return CasesApi.notice(id, value);
      if (m === "note") return CasesApi.note(id, value);
      if (m === "escalate") return CasesApi.escalate(id, value);
      return CasesApi.close(id, value);
    },
    onSuccess: (c) => {
      qc.setQueryData(key, c);
      qc.invalidateQueries({ queryKey: ["oversight"], predicate: (q) => q.queryKey[1] !== "case" });
      setMode(null);
      setText("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "That didn't work. Try again."),
  });

  const back = `/app/${user?.role}/oversight`;

  if (isLoading) {
    return (
      <div>
        <Skeleton className="mb-4 h-10 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (isError || !data) {
    const notFound = loadError instanceof ApiError && loadError.status === 404;
    return (
      <div>
        <BackLink to={back} />
        <ErrorState
          message={notFound ? "This case doesn't exist, or it isn't in your jurisdiction." : "Couldn't load this case."}
          onRetry={notFound ? undefined : () => refetch()}
        />
      </div>
    );
  }

  const c = data;
  const active = c.status !== "resolved";
  const next = NEXT_LEVEL[c.level];
  const submit = () => {
    if (!mode) return;
    const value = text.trim();
    if (FORM[mode].required && !value) {
      setError(mode === "close" ? "Give a reason for closing the case." : "Write something first.");
      return;
    }
    setError(null);
    act.mutate({ m: mode, value });
  };

  return (
    <div>
      <BackLink to={back} />
      <PageHeader
        title={c.instrument.uiid ?? "Enforcement case"}
        description={`${c.instrument.type ?? "Instrument"} · ${KIND_LABEL[c.kind]}`}
        action={
          <div className="flex flex-wrap gap-2 sm:justify-end">
            <CaseStatusBadge status={c.status} />
            {active && <LevelBadge level={c.level} />}
          </div>
        }
      />

      {!active && (
        <div role="status" className="mb-4 rounded-xl border border-success/30 bg-success-50 p-4 text-sm text-success">
          <span className="font-semibold">Resolved.</span> {c.resolution ? RESOLUTION_LABEL[c.resolution] : "Closed"}
          {c.resolved_at ? ` on ${dateOnly(c.resolved_at)}.` : "."} No further action is needed.
        </div>
      )}
      {c.escalation_due && (
        <div role="status" className="mb-4 rounded-xl border border-warning/30 bg-warning-50 p-4 text-sm text-ink">
          <span className="font-semibold text-warning">Due for escalation.</span> The last notice is more than{" "}
          {c.escalation_after_days} days old and nothing has changed. It will move up automatically
          {next ? `, or you can send it to ${LEVEL_LABEL[next]} now.` : "."}
        </div>
      )}

      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-5 lg:items-start">
        {/* Actions come first on a phone, to the right of the timeline on a large screen. */}
        <div className="flex flex-col gap-4 lg:col-span-2 lg:col-start-4 lg:row-start-1">
          <Panel className="p-4 sm:p-5">
            <h2 className="font-display text-lg text-ink">{mode ? FORM[mode].title : "What do you want to do?"}</h2>
            {!active ? (
              <p className="mt-2 text-sm text-slate-600">This case is closed.</p>
            ) : mode ? (
              <div className="mt-3">
                <TextArea
                  label={FORM[mode].label}
                  hint={FORM[mode].hint}
                  value={text}
                  maxLength={mode === "note" ? 1000 : 500}
                  onChange={(e) => setText(e.target.value)}
                  autoFocus
                />
                {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
                <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                  <Button
                    variant={FORM[mode].danger ? "danger" : "primary"}
                    loading={act.isPending}
                    onClick={submit}
                    className="sm:flex-1"
                  >
                    {mode === "escalate" && next ? `Escalate to ${LEVEL_LABEL[next]}` : FORM[mode].confirm}
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={act.isPending}
                    onClick={() => {
                      setMode(null);
                      setText("");
                      setError(null);
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="mt-3 flex flex-col gap-2">
                <Button disabled={!c.can.notice} onClick={() => setMode("notice")}>
                  Send notice to owner
                </Button>
                {c.can.notice_available_on && (
                  <p className="-mt-1 text-xs text-slate-500">
                    A notice went out recently. The next one can be sent on {dateOnly(c.can.notice_available_on)}.
                  </p>
                )}
                <Button variant="secondary" disabled={!c.can.note} onClick={() => setMode("note")}>
                  Add a note
                </Button>
                {next && (
                  <Button variant="secondary" disabled={!c.can.escalate} onClick={() => setMode("escalate")}>
                    Escalate to {LEVEL_LABEL[next]}
                  </Button>
                )}
                <Button variant="ghost" disabled={!c.can.close} onClick={() => setMode("close")}>
                  Close case
                </Button>
                {!c.can.close && (
                  <p className="text-xs text-slate-500">
                    This case is with {LEVEL_LABEL[c.level]} now. You can add notes, but only they can send notices, escalate or close it.
                  </p>
                )}
              </div>
            )}
          </Panel>

          <Facts c={c} />
        </div>

        <Panel className="p-4 sm:p-5 lg:col-span-3 lg:col-start-1 lg:row-start-1">
          <h2 className="font-display text-lg text-ink">Timeline</h2>
          <ol className="mt-4">
            {[...c.events].reverse().map((e, i, all) => (
              <TimelineItem key={`${e.at}-${i}`} e={e} last={i === all.length - 1} />
            ))}
          </ol>
        </Panel>
      </div>
    </div>
  );
}

function BackLink({ to }: { to: string }) {
  return (
    <Link to={to} className="mb-3 inline-flex h-10 items-center gap-1 text-sm font-medium text-teal hover:underline sm:h-auto">
      <span aria-hidden="true">←</span> Back to Oversight
    </Link>
  );
}

function Facts({ c }: { c: CaseDetail }) {
  const rows: [string, string | null][] = [
    ["Owner", [c.owner.org_name, c.owner.name].filter(Boolean).join(" · ") || null],
    ["Location", [c.district_name, c.state_name].filter(Boolean).join(", ") || null],
    ["Address", c.instrument.address_line],
    c.kind === "lapsed"
      ? ["Certificate", c.cert_no ? `${c.cert_no}${c.valid_until ? `, expired ${dateOnly(c.valid_until)}` : ""}` : null]
      : ["Registered", c.registered_on ? dateOnly(c.registered_on) : null],
    ["Opened", `${dateOnly(c.opened_at)}${c.opened_by_name ? ` by ${c.opened_by_name}` : ""}`],
    ["Notices sent", c.notice_count ? `${c.notice_count}${c.last_notice_at ? `, last on ${dateOnly(c.last_notice_at)}` : ""}` : "None yet"],
  ];
  return (
    <Panel className="p-4 sm:p-5">
      <h2 className="font-display text-lg text-ink">Details</h2>
      <dl className="mt-3 divide-y divide-line text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-start justify-between gap-4 py-2 first:pt-0 last:pb-0">
            <dt className="shrink-0 text-xs uppercase tracking-wide text-slate-500">{label}</dt>
            <dd className="min-w-0 break-words text-right text-ink">{value || "-"}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

const DOT: Record<CaseEvent["action"], string> = {
  opened: "bg-info",
  notice: "bg-warning",
  note: "bg-slate-400",
  escalated: "bg-danger",
  resolved: "bg-success",
};

function eventTitle(e: CaseEvent): string {
  switch (e.action) {
    case "opened":
      return "Case opened";
    case "notice":
      return "Notice sent to the owner";
    case "note":
      return "Note added";
    case "escalated":
      return `Escalated to ${e.to_level ? LEVEL_LABEL[e.to_level] : "the next level"}`;
    default:
      return e.by_name ? "Case closed" : "Case resolved";
  }
}

function TimelineItem({ e, last }: { e: CaseEvent; last: boolean }) {
  const who = e.by_name ? `${e.by_name}${e.by_role ? ` (${e.by_role === "admin" ? "Admin" : e.by_role.toUpperCase()})` : ""}` : "Automatic";
  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {!last && <span className="absolute left-[5px] top-4 h-full w-px bg-line" aria-hidden="true" />}
      <span className={cn("relative mt-1.5 h-3 w-3 shrink-0 rounded-full ring-4 ring-white", DOT[e.action])} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink">{eventTitle(e)}</p>
        <p className="text-xs text-slate-500">
          {who} · {dateTime(e.at)}
        </p>
        {e.text && <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-700">{e.text}</p>}
        {e.action === "notice" && (
          <div className="mt-1">
            {e.emailed ? <Badge tone="success">Emailed to owner</Badge> : <Badge tone="neutral">Not emailed, visible in the owner's app</Badge>}
          </div>
        )}
      </div>
    </li>
  );
}
