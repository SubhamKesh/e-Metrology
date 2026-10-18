import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { Panel, StatCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ExportButtons } from "@/components/domain/ExportButtons";
import { CaseCell } from "@/components/domain/CaseCell";
import { CaseStatusBadge, KIND_LABEL, LevelBadge } from "@/components/domain/CaseBadges";
import { SelectInput } from "@/components/ui/Field";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { ApplicationStatusBadge, Badge } from "@/components/ui/StatusBadge";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/cn";
import { CasesApi, GeoApi, OversightApi } from "@/lib/endpoints";
import type { CaseKind, CaseListItem, DistrictRow, EnforcementBand, EnforcementItem, PendencyReport, UncertifiedItem } from "@/lib/types";

type Tab = "pendency" | "districts" | "enforcement" | "cases";

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "pendency", label: "Pendency ageing", hint: "Applications still waiting, by how long" },
  { id: "districts", label: "District-wise", hint: "Instruments and applications per district" },
  { id: "enforcement", label: "Enforcement", hint: "Instruments with a lapsed certificate, or never certified" },
  { id: "cases", label: "Cases", hint: "Notices sent to owners and cases passed up to senior officers" },
];

const PAGE_SIZE = 25;
const fmt = (n: number) => n.toLocaleString("en-IN");
const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium" });

const BAND_TONE: Record<EnforcementBand, "warning" | "danger" | "neutral"> = {
  recent: "neutral",
  overdue: "warning",
  long_overdue: "danger",
};

// Pendency ageing, district-wise position and the enforcement list. Admins see the whole country;
// LMO / GATC officers see their own jurisdiction (the server decides, the page only asks).
export default function Oversight() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState<Tab>("pendency");
  const [stateCode, setStateCode] = useState("");
  const [districtCode, setDistrictCode] = useState("");
  const active = TABS.find((t) => t.id === tab)!;
  const place = { state_code: stateCode || undefined, district_code: districtCode || undefined };

  const states = useQuery({ queryKey: ["geo", "states"], queryFn: GeoApi.states, enabled: isAdmin, staleTime: 3_600_000 });
  const districts = useQuery({
    queryKey: ["geo", "districts", stateCode],
    queryFn: () => GeoApi.districts(stateCode),
    enabled: isAdmin && !!stateCode,
    staleTime: 3_600_000,
  });

  return (
    <div>
      <PageHeader
        title="Oversight"
        description={isAdmin ? "Pendency, district position, enforcement and cases across the registry." : "Pendency, district position, enforcement and cases in your jurisdiction."}
      />

      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div role="tablist" aria-label="Oversight view" className="inline-flex gap-1 rounded-lg border border-line bg-white p-1 shadow-panel">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              type="button"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "h-10 whitespace-nowrap rounded-md px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40",
                tab === t.id ? "bg-teal text-white" : "text-slate-600 hover:bg-paper2",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-500">{active.hint}</p>

      {isAdmin && (
        <div className="mt-4 grid gap-4 rounded-xl border border-line bg-white p-4 shadow-panel sm:grid-cols-2 lg:grid-cols-4">
          <SelectInput
            label="State / UT"
            value={stateCode}
            onChange={(e) => {
              setStateCode(e.target.value);
              setDistrictCode("");
            }}
            options={[{ value: "", label: "All states and UTs" }, ...(states.data ?? []).map((s) => ({ value: s.code, label: s.name }))]}
          />
          <SelectInput
            label="District"
            value={districtCode}
            disabled={!stateCode}
            onChange={(e) => setDistrictCode(e.target.value)}
            options={[{ value: "", label: stateCode ? "All districts" : "Pick a state first" }, ...(districts.data ?? []).map((d) => ({ value: d.code, label: d.name }))]}
          />
        </div>
      )}

      <div className="mt-4" role="tabpanel">
        {tab === "pendency" && <PendencyView place={place} />}
        {tab === "districts" && <DistrictsView place={place} />}
        {tab === "enforcement" && <EnforcementTab place={place} />}
        {tab === "cases" && <CasesView place={place} />}
      </div>
    </div>
  );
}

type Place = { state_code?: string; district_code?: string };

function Loading() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-28 w-full" />
      ))}
    </div>
  );
}

function GeneratedAt({ iso }: { iso: string }) {
  return (
    <p className="mt-3 text-xs text-slate-500">
      As of {new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" })} IST
    </p>
  );
}

// ------------------------------------------------------------------ pendency ageing

function PendencyView({ place }: { place: Place }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["oversight", "pendency", place],
    queryFn: () => OversightApi.pendency(place),
    placeholderData: keepPreviousData,
  });
  if (isLoading) return <Loading />;
  if (isError || !data) return <ErrorState message="Couldn't load pendency data." onRetry={() => refetch()} />;

  const maxCount = Math.max(...data.buckets.map((b) => b.count), 1);
  const columns: Column<PendencyReport["oldest"][number]>[] = [
    { header: "UIID", cell: (r) => <span className="font-mono text-xs">{r.uiid ?? "-"}</span> },
    { header: "Instrument", cell: (r) => r.instrument_type ?? "-" },
    { header: "District", cell: (r) => [r.district_name, r.state_name].filter(Boolean).join(", ") || "-" },
    { header: "Status", cell: (r) => <ApplicationStatusBadge status={r.status} /> },
    { header: "Waiting", cell: (r) => <span className="tabular">{r.age_days} d</span> },
    { header: "Officer", cell: (r) => (r.assigned ? "Assigned" : <Badge tone="warning">Unassigned</Badge>) },
  ];

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard label="Open applications" value={fmt(data.total_open)} tone="info" />
        <StatCard label={`Waiting over ${data.target_days} days`} value={fmt(data.over_target)} tone={data.over_target ? "danger" : "success"} />
        <StatCard label="Not yet assigned" value={fmt(data.unassigned)} tone={data.unassigned ? "warning" : "neutral"} />
        <StatCard
          label="Submitted / scheduled / inspected"
          value={`${fmt(data.by_status.submitted)} / ${fmt(data.by_status.scheduled)} / ${fmt(data.by_status.inspected)}`}
        />
      </div>

      <Panel className="mt-6 p-4 sm:p-6">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="font-display text-lg text-ink">How long applications have waited</h2>
            <span className="text-xs text-slate-500">Days since submission, open applications only</span>
          </div>
          <ExportButtons kind="oversight-pendency" params={place} keeps="longest-waiting" disabled={data.total_open === 0} />
        </div>
        <ul className="flex flex-col gap-3">
          {data.buckets.map((b) => (
            <li key={b.label} className="grid grid-cols-[minmax(0,6rem)_1fr_auto] items-center gap-3 sm:grid-cols-[8rem_1fr_4rem]">
              <span className="truncate text-sm text-slate-600">{b.label}</span>
              <div className="h-2.5 rounded-full bg-paper2" role="presentation">
                <div
                  className={cn("h-2.5 rounded-full", b.min_days > data.target_days ? "bg-danger" : "bg-teal")}
                  style={{ width: `${(b.count / maxCount) * 100}%` }}
                />
              </div>
              <span className="text-right text-sm tabular text-ink" title={`Submitted ${b.by_status.submitted}, scheduled ${b.by_status.scheduled}, inspected ${b.by_status.inspected}`}>
                {fmt(b.count)}
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel className="mt-6 p-4 sm:p-6">
        <h2 className="mb-3 font-display text-lg text-ink">Longest waiting</h2>
        <DataTable
          columns={columns}
          rows={data.oldest}
          rowKey={(r) => r.application_id}
          emptyTitle="No open applications"
          emptyDescription="Nothing is waiting here right now."
          onRowClick={(r) => navigate(`/app/${user?.role}/applications/${r.application_id}`)}
        />
      </Panel>
      <GeneratedAt iso={data.generated_at} />
    </>
  );
}

// ------------------------------------------------------------------ district-wise

function DistrictsView({ place }: { place: Place }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["oversight", "districts", place],
    queryFn: () => OversightApi.districts(place),
    placeholderData: keepPreviousData,
  });
  if (isLoading) return <Loading />;
  if (isError || !data) return <ErrorState message="Couldn't load district data." onRetry={() => refetch()} />;

  const num = (n: number) => <span className="tabular">{fmt(n)}</span>;
  const columns: Column<DistrictRow>[] = [
    { header: "District", cell: (r) => <span className="font-medium text-ink">{r.district_name}</span> },
    { header: "State / UT", cell: (r) => r.state_name },
    { header: "Instruments", cell: (r) => num(r.instruments) },
    { header: "Open", cell: (r) => num(r.open_applications) },
    {
      header: `Over ${data.target_days} days`,
      cell: (r) => (r.overdue_applications ? <Badge tone="danger">{fmt(r.overdue_applications)}</Badge> : num(0)),
    },
    { header: "Verified", cell: (r) => num(r.verified) },
    { header: "Expired", cell: (r) => num(r.expired) },
  ];

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard label="Instruments" value={fmt(data.totals.instruments)} />
        <StatCard label="Open applications" value={fmt(data.totals.open_applications)} tone="info" />
        <StatCard label={`Open over ${data.target_days} days`} value={fmt(data.totals.overdue_applications)} tone={data.totals.overdue_applications ? "danger" : "success"} />
        <StatCard label="Expired" value={fmt(data.totals.expired)} tone="warning" />
      </div>
      <Panel className="mt-6 p-4 sm:p-6">
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="font-display text-lg text-ink">District-wise position</h2>
            <span className="text-xs text-slate-500">Most overdue first. Verified and expired count applications.</span>
          </div>
          <ExportButtons kind="oversight-districts" params={place} disabled={data.rows.length === 0} />
        </div>
        <DataTable
          columns={columns}
          rows={data.rows}
          rowKey={(r) => `${r.state_code}/${r.district_code}`}
          emptyTitle="No districts to show"
          emptyDescription="No instruments or applications match this view."
        />
      </Panel>
      <GeneratedAt iso={data.generated_at} />
    </>
  );
}

// ------------------------------------------------------------------ enforcement

function LapsedView({ place }: { place: Place }) {
  const [reverification, setReverification] = useState<"" | "applied" | "none">("");
  const [minDays, setMinDays] = useState("0");
  const [page, setPage] = useState(1);
  const query = {
    ...place,
    reverification: reverification || undefined,
    min_days_overdue: Number(minDays) || undefined,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ["oversight", "enforcement", query],
    queryFn: () => OversightApi.enforcement(query),
    placeholderData: keepPreviousData,
  });

  // Changing a filter, or the place chosen above, starts again from page 1.
  const [lastPlace, setLastPlace] = useState(JSON.stringify(place));
  if (lastPlace !== JSON.stringify(place)) {
    setLastPlace(JSON.stringify(place));
    setPage(1);
  }

  if (isLoading) return <Loading />;
  if (isError || !data) return <ErrorState message="Couldn't load the enforcement list." onRetry={() => refetch()} />;

  const columns: Column<EnforcementItem>[] = [
    {
      header: "Instrument",
      cell: (r) => (
        <div>
          <span className="font-mono text-xs">{r.uiid ?? "-"}</span>
          <div className="text-xs text-slate-500">{r.instrument_type ?? "-"}</div>
        </div>
      ),
    },
    {
      header: "Owner",
      cell: (r) => (
        <div>
          {r.org_name || r.owner_name || "-"}
          {r.org_name && r.owner_name && <div className="text-xs text-slate-500">{r.owner_name}</div>}
        </div>
      ),
    },
    {
      header: "Location",
      cell: (r) => (
        <div>
          {[r.district_name, r.state_name].filter(Boolean).join(", ") || "-"}
          {r.address_line && <div className="max-w-[16rem] truncate text-xs text-slate-500" title={r.address_line}>{r.address_line}</div>}
        </div>
      ),
    },
    { header: "Certificate", cell: (r) => <span className="font-mono text-xs">{r.cert_no ?? "-"}</span> },
    {
      header: "Lapsed",
      cell: (r) => (
        <div>
          {formatDate(r.valid_until)}
          <div className="mt-0.5">
            <Badge tone={BAND_TONE[r.band]}>{r.days_overdue} d ago</Badge>
          </div>
        </div>
      ),
    },
    {
      header: "Re-verification",
      cell: (r) =>
        r.reverification ? (
          <div>
            <Badge tone="info">Applied {formatDate(r.reverification.applied_on)}</Badge>
            <div className="mt-0.5"><ApplicationStatusBadge status={r.reverification.status} /></div>
          </div>
        ) : (
          <Badge tone="danger">Not applied</Badge>
        ),
    },
    { header: "Case", cell: (r) => <CaseCell instrumentId={r.instrument_id} caseRef={r.case} /> },
  ];

  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  const s = data.summary;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard label="Lapsed certificates" value={fmt(s.lapsed)} tone={s.lapsed ? "danger" : "success"} />
        <StatCard label="Not applied to renew" value={fmt(s.no_reverification)} tone={s.no_reverification ? "danger" : "neutral"} />
        <StatCard label="Re-verification applied" value={fmt(s.reverification_applied)} tone="info" />
        <StatCard label="Lapsed over 90 days" value={fmt(s.long_overdue)} tone={s.long_overdue ? "warning" : "neutral"} detail={`${fmt(s.overdue)} for 31-90 days, ${fmt(s.recent)} up to 30`} />
      </div>

      <div className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-4 shadow-panel sm:grid-cols-2 lg:grid-cols-4">
        <SelectInput
          label="Re-verification"
          value={reverification}
          onChange={(e) => { setReverification(e.target.value as "" | "applied" | "none"); setPage(1); }}
          options={[
            { value: "", label: "Any" },
            { value: "none", label: "Not applied" },
            { value: "applied", label: "Applied, pending" },
          ]}
        />
        <SelectInput
          label="Lapsed for"
          value={minDays}
          onChange={(e) => { setMinDays(e.target.value); setPage(1); }}
          options={[
            { value: "0", label: "Any time" },
            { value: "31", label: "More than 30 days" },
            { value: "91", label: "More than 90 days" },
          ]}
        />
      </div>

      <Panel className="mt-4 p-4 sm:p-6">
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="font-display text-lg text-ink">Instruments without a valid certificate</h2>
            <span className="text-xs text-slate-500">Longest lapsed first. Applying to renew does not make the certificate valid.</span>
          </div>
          <ExportButtons
            kind="oversight-enforcement"
            params={{ ...place, reverification: reverification || undefined, min_days_overdue: Number(minDays) || undefined }}
            keeps="most overdue"
            disabled={data.total === 0}
          />
        </div>
        <DataTable
          columns={columns}
          rows={data.items}
          rowKey={(r) => r.instrument_id}
          emptyTitle="No lapsed certificates"
          emptyDescription="Nothing matches these filters."
        />
        {data.truncated && (
          <p className="mt-3 text-xs text-warning">This list hit its safety limit, so only the most overdue instruments are shown. Narrow it by state or district to see the rest.</p>
        )}
        {data.total > data.page_size && (
          <div className="mt-4 flex items-center justify-between gap-3">
            <Button variant="secondary" size="sm" disabled={page <= 1 || isFetching} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className="text-sm text-slate-600">Page {data.page} of {pages}</span>
            <Button variant="secondary" size="sm" disabled={page >= pages || isFetching} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        )}
      </Panel>
      <GeneratedAt iso={data.generated_at} />
    </>
  );
}

// ---------------------------------------------------------------- enforcement: lapsed / never certified

function EnforcementTab({ place }: { place: Place }) {
  const [list, setList] = useState<"lapsed" | "uncertified">("lapsed");
  const options = [
    { id: "lapsed" as const, label: "Lapsed certificates" },
    { id: "uncertified" as const, label: "Never certified" },
  ];
  return (
    <>
      <div role="group" aria-label="Enforcement list" className="mb-4 inline-flex gap-1 rounded-lg border border-line bg-white p-1 shadow-panel">
        {options.map((o) => (
          <button
            key={o.id}
            type="button"
            aria-pressed={list === o.id}
            onClick={() => setList(o.id)}
            className={cn(
              "h-10 whitespace-nowrap rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40 sm:px-4",
              list === o.id ? "bg-ink text-white" : "text-slate-600 hover:bg-paper2",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
      {list === "lapsed" ? <LapsedView place={place} /> : <UncertifiedView place={place} />}
    </>
  );
}

function Pager({ page, total, pageSize, fetching, onPage }: { page: number; total: number; pageSize: number; fetching: boolean; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;
  return (
    <div className="mt-4 flex items-center justify-between gap-3">
      <Button variant="secondary" size="sm" disabled={page <= 1 || fetching} onClick={() => onPage(page - 1)}>
        Previous
      </Button>
      <span className="text-sm text-slate-600">Page {page} of {pages}</span>
      <Button variant="secondary" size="sm" disabled={page >= pages || fetching} onClick={() => onPage(page + 1)}>
        Next
      </Button>
    </div>
  );
}

function UncertifiedView({ place }: { place: Place }) {
  const [application, setApplication] = useState<"" | "applied" | "none">("");
  const [minDays, setMinDays] = useState("0");
  const [page, setPage] = useState(1);
  const query = {
    ...place,
    application: application || undefined,
    min_days: Number(minDays) || undefined,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ["oversight", "uncertified", query],
    queryFn: () => OversightApi.uncertified(query),
    placeholderData: keepPreviousData,
  });

  const [lastPlace, setLastPlace] = useState(JSON.stringify(place));
  if (lastPlace !== JSON.stringify(place)) {
    setLastPlace(JSON.stringify(place));
    setPage(1);
  }

  if (isLoading) return <Loading />;
  if (isError || !data) return <ErrorState message="Couldn't load the never-certified list." onRetry={() => refetch()} />;

  const s = data.summary;
  const columns: Column<UncertifiedItem>[] = [
    {
      header: "Instrument",
      cell: (r) => (
        <div>
          <span className="font-mono text-xs">{r.uiid ?? "-"}</span>
          <div className="text-xs text-slate-500">{r.instrument_type ?? "-"}</div>
        </div>
      ),
    },
    {
      header: "Owner",
      cell: (r) => (
        <div>
          {r.org_name || r.owner_name || "-"}
          {r.org_name && r.owner_name && <div className="text-xs text-slate-500">{r.owner_name}</div>}
        </div>
      ),
    },
    {
      header: "Location",
      cell: (r) => (
        <div>
          {[r.district_name, r.state_name].filter(Boolean).join(", ") || "-"}
          {r.address_line && <div className="max-w-[16rem] truncate text-xs text-slate-500" title={r.address_line}>{r.address_line}</div>}
        </div>
      ),
    },
    {
      header: "Registered",
      cell: (r) => (
        <div>
          {formatDate(r.registered_on)}
          <div className="mt-0.5">
            <Badge tone={r.days_since_registered > 90 ? "danger" : "warning"}>{r.days_since_registered} d ago</Badge>
          </div>
        </div>
      ),
    },
    {
      header: "Application",
      cell: (r) =>
        r.application ? (
          <div>
            <Badge tone="info">Applied {formatDate(r.application.applied_on)}</Badge>
            <div className="mt-0.5"><ApplicationStatusBadge status={r.application.status} /></div>
          </div>
        ) : (
          <Badge tone="danger">Not applied</Badge>
        ),
    },
    { header: "Case", cell: (r) => <CaseCell instrumentId={r.instrument_id} caseRef={r.case} /> },
  ];

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard label="Never certified" value={fmt(s.total)} tone={s.total ? "danger" : "success"} />
        <StatCard label="Not applied" value={fmt(s.not_applied)} tone={s.not_applied ? "danger" : "neutral"} />
        <StatCard label="Application pending" value={fmt(s.applied)} tone="info" />
        <StatCard label="Counted after" value={`${data.grace_days} days`} detail="Registered longer ago than this" />
      </div>

      <div className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-4 shadow-panel sm:grid-cols-2 lg:grid-cols-4">
        <SelectInput
          label="Application"
          value={application}
          onChange={(e) => { setApplication(e.target.value as "" | "applied" | "none"); setPage(1); }}
          options={[
            { value: "", label: "Any" },
            { value: "none", label: "Not applied" },
            { value: "applied", label: "Applied, pending" },
          ]}
        />
        <SelectInput
          label="Registered for"
          value={minDays}
          onChange={(e) => { setMinDays(e.target.value); setPage(1); }}
          options={[
            { value: "0", label: "Any time" },
            { value: "61", label: "More than 60 days" },
            { value: "91", label: "More than 90 days" },
          ]}
        />
      </div>

      <Panel className="mt-4 p-4 sm:p-6">
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="font-display text-lg text-ink">Instruments that were never verified</h2>
            <span className="text-xs text-slate-500">
              Registered more than {data.grace_days} days ago with no certificate, longest first. An application in progress is
              shown, but the instrument is still not verified.
            </span>
          </div>
          <ExportButtons
            kind="oversight-uncertified"
            params={{ ...place, application: application || undefined, min_days: Number(minDays) || undefined }}
            keeps="longest registered"
            disabled={data.total === 0}
          />
        </div>
        <DataTable
          columns={columns}
          rows={data.items}
          rowKey={(r) => r.instrument_id}
          emptyTitle="No unverified instruments"
          emptyDescription="Nothing matches these filters."
        />
        {data.truncated && (
          <p className="mt-3 text-xs text-warning">This list hit its safety limit, so only the longest-registered instruments are shown. Narrow it by state or district to see the rest.</p>
        )}
        <Pager page={data.page} total={data.total} pageSize={data.page_size} fetching={isFetching} onPage={setPage} />
      </Panel>
      <GeneratedAt iso={data.generated_at} />
    </>
  );
}

// ---------------------------------------------------------------- cases

type CaseView = "active" | "mine" | "due" | "resolved" | "all";

const CASE_VIEWS: { value: CaseView; label: string }[] = [
  { value: "active", label: "All open cases" },
  { value: "mine", label: "With me" },
  { value: "due", label: "Due for escalation" },
  { value: "resolved", label: "Resolved" },
  { value: "all", label: "Everything" },
];

function CasesView({ place }: { place: Place }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [view, setView] = useState<CaseView>("active");
  const [kind, setKind] = useState<"" | CaseKind>("");
  const [page, setPage] = useState(1);
  const query = {
    ...place,
    status: view === "resolved" ? ("resolved" as const) : view === "all" ? ("all" as const) : view === "due" ? undefined : ("active" as const),
    due: view === "due" || undefined,
    with_me: view === "mine" || undefined,
    kind: kind || undefined,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ["oversight", "cases", query],
    queryFn: () => CasesApi.list(query),
    placeholderData: keepPreviousData,
  });

  const [lastPlace, setLastPlace] = useState(JSON.stringify(place));
  if (lastPlace !== JSON.stringify(place)) {
    setLastPlace(JSON.stringify(place));
    setPage(1);
  }

  if (isLoading) return <Loading />;
  if (isError || !data) return <ErrorState message="Couldn't load the cases." onRetry={() => refetch()} />;

  const s = data.summary;
  const go = (c: CaseListItem) => navigate(`/app/${user?.role}/oversight/cases/${c.id}`);
  const columns: Column<CaseListItem>[] = [
    {
      header: "Instrument",
      cell: (r) => (
        <div>
          <span className="font-mono text-xs">{r.instrument.uiid ?? "-"}</span>
          <div className="text-xs text-slate-500">{r.instrument.type ?? "-"}</div>
        </div>
      ),
    },
    {
      header: "Owner",
      cell: (r) => r.owner.org_name || r.owner.name || "-",
    },
    {
      header: "Location",
      cell: (r) => [r.district_name, r.state_name].filter(Boolean).join(", ") || "-",
    },
    {
      header: "Case",
      cell: (r) => (
        <div className="flex flex-col items-start gap-1">
          <span className="text-xs text-slate-500">{KIND_LABEL[r.kind]}</span>
          <div className="flex flex-wrap gap-1">
            <CaseStatusBadge status={r.status} />
            {r.status !== "resolved" && <LevelBadge level={r.level} />}
            {r.escalation_due && <Badge tone="warning">Due for escalation</Badge>}
          </div>
        </div>
      ),
    },
    {
      header: "Notices",
      cell: (r) => (r.notice_count ? `${r.notice_count}${r.last_notice_at ? `, last ${formatDate(r.last_notice_at)}` : ""}` : "None yet"),
    },
    {
      header: "",
      className: "text-right",
      cell: (r) => (
        <Button variant="secondary" size="sm" onClick={() => go(r)}>
          Open
        </Button>
      ),
    },
  ];

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard label="Open cases" value={fmt(s.active)} tone={s.active ? "info" : "neutral"} detail={`${fmt(s.notice_sent)} notice sent, ${fmt(s.escalated)} escalated`} />
        <StatCard label="With me" value={fmt(s.with_me)} tone={s.with_me ? "warning" : "neutral"} detail="Waiting for your action" />
        <StatCard label="Due for escalation" value={fmt(s.escalation_due)} tone={s.escalation_due ? "danger" : "neutral"} />
        <StatCard label="Resolved" value={fmt(s.resolved)} tone="success" />
      </div>

      <div className="mt-6 grid gap-4 rounded-xl border border-line bg-white p-4 shadow-panel sm:grid-cols-2 lg:grid-cols-4">
        <SelectInput
          label="Show"
          value={view}
          onChange={(e) => { setView(e.target.value as CaseView); setPage(1); }}
          options={CASE_VIEWS}
        />
        <SelectInput
          label="Type"
          value={kind}
          onChange={(e) => { setKind(e.target.value as "" | CaseKind); setPage(1); }}
          options={[
            { value: "", label: "All types" },
            { value: "lapsed", label: "Lapsed certificate" },
            { value: "never_certified", label: "Never certified" },
          ]}
        />
      </div>

      <Panel className="mt-4 p-4 sm:p-6">
        <div className="mb-3">
          <h2 className="font-display text-lg text-ink">Enforcement cases</h2>
          <span className="text-xs text-slate-500">
            Open a case from the Enforcement tab. A case closes by itself once the instrument has a valid certificate.
          </span>
        </div>
        <DataTable
          columns={columns}
          rows={data.items}
          rowKey={(r) => r.id}
          onRowClick={go}
          emptyTitle="No cases here"
          emptyDescription="Open a case from the Enforcement tab to send a notice to an owner."
        />
        <Pager page={data.page} total={data.total} pageSize={data.page_size} fetching={isFetching} onPage={setPage} />
      </Panel>
      <GeneratedAt iso={data.generated_at} />
    </>
  );
}
