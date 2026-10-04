import { type FormEvent, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/AppShell";
import { Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TextInput, SelectInput } from "@/components/ui/Field";
import { DataTable } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/States";
import { Badge } from "@/components/ui/StatusBadge";
import { AdminAuditApi, type AuditLogQuery } from "@/lib/endpoints";
import { ApiError } from "@/lib/api";
import type { AuditLogEntry, AuditOutcome } from "@/lib/types";

const PAGE_SIZE = 25;

const OUTCOME_TONE: Record<AuditOutcome, "success" | "danger" | "warning" | "neutral"> = {
  success: "success",
  failure: "danger",
  blocked: "warning",
  ignored: "neutral",
};

const OUTCOME_OPTIONS = [
  { value: "", label: "Any outcome" },
  { value: "success", label: "Success" },
  { value: "failure", label: "Failure" },
  { value: "blocked", label: "Blocked" },
  { value: "ignored", label: "Ignored" },
];

const ROLE_OPTIONS = [
  { value: "", label: "Any role" },
  { value: "owner", label: "Business owner" },
  { value: "lmo", label: "Legal Metrology Officer" },
  { value: "gatc", label: "GATC" },
  { value: "admin", label: "Admin" },
];

// The server stores UTC; officials read it in Indian Standard Time.
const formatIst = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "medium" });

// "password_reset_failed" -> "Password reset failed"
const humanize = (event: string) => {
  const text = event.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};

interface Filters {
  event: string;
  outcome: string;
  role: string;
  search: string;
  date_from: string;
  date_to: string;
}

const EMPTY_FILTERS: Filters = { event: "", outcome: "", role: "", search: "", date_from: "", date_to: "" };

export default function AdminAuditLog() {
  // `draft` is what's in the form; `applied` is what the table is showing, so
  // typing in a box doesn't fire a request per keystroke.
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);

  const query: AuditLogQuery = { ...applied, page, page_size: PAGE_SIZE };
  const { data, isLoading, isFetching, isError, error, refetch } = useQuery({
    queryKey: ["admin", "audit-logs", applied, page],
    queryFn: () => AdminAuditApi.list(query),
    placeholderData: keepPreviousData, // keep the old rows on screen while the next page loads
  });

  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => setDraft((d) => ({ ...d, [key]: value }));

  function onApply(e: FormEvent) {
    e.preventDefault();
    setApplied({ ...draft, search: draft.search.trim() });
    setPage(1);
  }

  function onReset() {
    setDraft(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setPage(1);
  }

  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);

  const eventOptions = [
    { value: "", label: "Any event" },
    ...(data?.events ?? []).map((e) => ({ value: e, label: humanize(e) })),
  ];

  const filterError =
    isError && error instanceof ApiError && (error.status === 400 || error.status === 422) ? error.message : null;

  return (
    <div>
      <PageHeader
        title="Audit log"
        description="A read-only record of sign-ins, password and two-step events, and administrator actions. Times are shown in IST. It never contains passwords, codes or tokens."
      />

      <Panel className="p-5">
        <form onSubmit={onApply} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SelectInput
            label="Event"
            value={draft.event}
            onChange={(e) => set("event", e.target.value)}
            options={eventOptions}
          />
          <SelectInput
            label="Outcome"
            value={draft.outcome}
            onChange={(e) => set("outcome", e.target.value)}
            options={OUTCOME_OPTIONS}
          />
          <SelectInput
            label="Role"
            value={draft.role}
            onChange={(e) => set("role", e.target.value)}
            options={ROLE_OPTIONS}
          />
          <TextInput
            label="Email contains"
            hint="Matches the account or the admin who acted."
            maxLength={100}
            value={draft.search}
            onChange={(e) => set("search", e.target.value)}
          />
          <TextInput
            label="From date"
            type="date"
            value={draft.date_from}
            onChange={(e) => set("date_from", e.target.value)}
          />
          <TextInput
            label="To date"
            type="date"
            value={draft.date_to}
            onChange={(e) => set("date_to", e.target.value)}
          />
          <div className="flex gap-2 sm:col-span-2 lg:col-span-3">
            <Button type="submit" loading={isFetching && !isLoading}>
              Apply filters
            </Button>
            <Button type="button" variant="secondary" onClick={onReset}>
              Reset
            </Button>
            <Button type="button" variant="secondary" onClick={() => refetch()} disabled={isFetching}>
              Refresh
            </Button>
          </div>
        </form>
        {filterError && <p className="mt-3 text-sm text-danger">{filterError}</p>}
      </Panel>

      <Panel className="mt-6 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-lg text-ink">Events</h2>
          <p className="text-sm text-slate-500" aria-live="polite">
            {data ? (total === 0 ? "No matching events" : `Showing ${from}–${to} of ${total}`) : ""}
          </p>
        </div>
        <div className="mt-4">
          {isError && !filterError ? (
            <ErrorState message="Couldn't load the audit log." onRetry={() => refetch()} />
          ) : (
            <DataTable
              isLoading={isLoading}
              rows={data?.items ?? []}
              rowKey={(row: AuditLogEntry) => row.id}
              emptyTitle="No events match these filters"
              emptyDescription="Try widening the date range or clearing a filter."
              columns={[
                { header: "Time (IST)", cell: (r: AuditLogEntry) => <span className="whitespace-nowrap">{formatIst(r.created_at)}</span> },
                { header: "Event", cell: (r: AuditLogEntry) => <span title={r.event}>{humanize(r.event)}</span> },
                {
                  header: "Outcome",
                  cell: (r: AuditLogEntry) => (
                    <Badge tone={OUTCOME_TONE[r.outcome] ?? "neutral"}>{r.outcome[0].toUpperCase() + r.outcome.slice(1)}</Badge>
                  ),
                },
                {
                  header: "Account",
                  cell: (r: AuditLogEntry) =>
                    r.email ? (
                      <span>
                        {r.email}
                        {r.role && <span className="ml-1 text-xs text-slate-500">({r.role})</span>}
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    ),
                },
                {
                  header: "Done by",
                  cell: (r: AuditLogEntry) =>
                    r.actor_email ?? (r.actor_id ? <span title={r.actor_id}>{r.actor_id}</span> : <span className="text-slate-400">—</span>),
                },
                { header: "Detail", cell: (r: AuditLogEntry) => r.detail ?? <span className="text-slate-400">—</span> },
                { header: "IP address", cell: (r: AuditLogEntry) => r.ip ?? <span className="text-slate-400">—</span> },
              ]}
            />
          )}
        </div>

        {total > PAGE_SIZE && (
          <div className="mt-4 flex items-center justify-between">
            <Button variant="secondary" size="sm" disabled={page <= 1 || isFetching} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className="text-sm text-slate-500">
              Page {page} of {lastPage}
            </span>
            <Button
              variant="secondary"
              size="sm"
              disabled={page >= lastPage || isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </Panel>
    </div>
  );
}
