import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/AppShell";
import { Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/StatusBadge";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { INSTRUMENT_TYPE_SPECS_KEY } from "@/hooks/useData";
import { ValidityApi } from "@/lib/endpoints";
import { ApiError } from "@/lib/api";
import type { ValidityRule, ValidityRules } from "@/lib/types";

const QUERY_KEY = ["admin", "validity"];

// The server stores UTC; officials read it in Indian Standard Time.
const formatIst = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium" });

/** "365" -> "1 year", "400" -> "400 days"; mirrors the label the server sends. */
function describe(days: number): string {
  if (days > 0 && days % 365 === 0) return days === 365 ? "1 year" : `${days / 365} years`;
  return `${days} ${days === 1 ? "day" : "days"}`;
}

function RuleRow({ rule, limits }: { rule: ValidityRule; limits: Pick<ValidityRules, "min_days" | "max_days"> }) {
  const qc = useQueryClient();
  const [value, setValue] = useState(String(rule.days));
  const [error, setError] = useState<string | null>(null);

  const days = Number(value);
  const valid = value.trim() !== "" && Number.isInteger(days) && days >= limits.min_days && days <= limits.max_days;
  const changed = valid && days !== rule.days;

  function refresh() {
    qc.invalidateQueries({ queryKey: QUERY_KEY });
    qc.invalidateQueries({ queryKey: INSTRUMENT_TYPE_SPECS_KEY });
  }
  const onError = (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not save. Please try again.");

  const save = useMutation({
    mutationFn: () => ValidityApi.set(rule.type, days),
    onSuccess: (saved) => {
      setError(null);
      setValue(String(saved.days));
      refresh();
    },
    onError,
  });
  const reset = useMutation({
    mutationFn: () => ValidityApi.reset(rule.type),
    onSuccess: (saved) => {
      setError(null);
      setValue(String(saved.days));
      refresh();
    },
    onError,
  });

  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="break-words font-medium text-ink">{rule.type}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-slate-500">
          <span>Now: {rule.label}</span>
          {rule.is_default ? (
            <Badge tone="neutral">Default</Badge>
          ) : (
            <Badge tone="info">Custom</Badge>
          )}
          {!rule.is_default && rule.updated_at && (
            <span>
              set {formatIst(rule.updated_at)}
              {rule.updated_by_name ? ` by ${rule.updated_by_name}` : ""}
            </span>
          )}
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor={`validity-${rule.type}`}>
            Validity in days for {rule.type}
          </label>
          <input
            id={`validity-${rule.type}`}
            type="number"
            inputMode="numeric"
            min={limits.min_days}
            max={limits.max_days}
            step={1}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              setError(null);
            }}
            aria-invalid={!valid || undefined}
            className={`h-11 w-28 rounded-md border bg-white px-3 text-sm text-ink focus:border-teal focus:outline-none focus:ring-2 focus:ring-teal/30 sm:h-10 ${
              valid ? "border-line" : "border-danger"
            }`}
          />
          <span className="text-sm text-slate-500">days{valid ? ` (${describe(days)})` : ""}</span>
          <Button size="sm" onClick={() => save.mutate()} disabled={!changed} loading={save.isPending}>
            Save
          </Button>
          {!rule.is_default && (
            <Button size="sm" variant="secondary" onClick={() => reset.mutate()} loading={reset.isPending}>
              Use default ({describe(rule.default_days)})
            </Button>
          )}
        </div>
        {!valid && (
          <p role="alert" className="text-sm text-danger">
            Enter a whole number of days between {limits.min_days} and {limits.max_days}.
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
      </div>
    </li>
  );
}

export default function AdminValidity() {
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: QUERY_KEY, queryFn: ValidityApi.list });

  return (
    <div>
      <PageHeader
        title="Certificate validity"
        description="How long a new certificate stays valid, for each type of instrument. A change applies only to certificates issued from now on; certificates already issued keep the expiry date printed on them."
      />

      {isError ? (
        <ErrorState message="Could not load the validity periods." onRetry={() => refetch()} />
      ) : isLoading || !data ? (
        <TableSkeleton cols={3} />
      ) : (
        <>
          <p className="mb-4 text-sm text-slate-600">
            Instruments without a custom period get the default of <span className="font-medium">{data.default_label}</span>{" "}
            ({data.default_days} days). A renewal issued while the old certificate is still valid continues from the old
            expiry date, with the period of the instrument&apos;s type. Allowed: {data.min_days} to {data.max_days} days.
          </p>
          <Panel>
            <ul className="divide-y divide-line">
              {data.items.map((rule) => (
                // Remount when the saved value changes so the input follows the server.
                <RuleRow key={`${rule.type}:${rule.days}`} rule={rule} limits={data} />
              ))}
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}
