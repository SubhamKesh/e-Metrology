import { useQuery } from "@tanstack/react-query";
import { ButtonLink } from "@/components/ui/Button";
import { NoticesApi } from "@/lib/endpoints";

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "long" });

// Notices an officer has sent about the owner's instruments. Shown only while the case is open, so a notice
// disappears by itself once the certificate is renewed (or the instrument is verified).
export function OwnerNotices() {
  const { data } = useQuery({ queryKey: ["notices", "mine"], queryFn: NoticesApi.mine, staleTime: 60_000 });
  if (!data || data.length === 0) return null;

  return (
    <section aria-label="Notices from Legal Metrology" className="mb-6 flex flex-col gap-3">
      {data.map((n) => (
        <div key={n.case_id} role="alert" className="rounded-xl border border-danger/30 bg-danger-50 p-4 sm:p-5">
          <p className="text-sm font-semibold text-danger">Notice from Legal Metrology, {formatDate(n.sent_at)}</p>
          <p className="mt-1 text-sm text-ink">
            {n.instrument_type ?? "Instrument"} · {n.uiid ?? ""}
          </p>
          <p className="mt-1 text-sm text-slate-700">
            {n.kind === "lapsed"
              ? "Your certificate has expired. Until it is renewed, this instrument must not be used for trade."
              : "This instrument has not been verified yet. It must not be used for trade until it is certified."}
          </p>
          {n.message && (
            <p className="mt-2 whitespace-pre-wrap break-words border-l-2 border-danger/40 pl-3 text-sm text-ink">
              {n.message}
              <span className="mt-0.5 block text-xs text-slate-500">{n.issued_by}</span>
            </p>
          )}
          <div className="mt-3 [&>a]:w-full sm:[&>a]:w-auto">
            <ButtonLink to={`/app/owner/applications/new?instrument=${n.instrument_id}`} size="sm">
              {n.kind === "lapsed" ? "Renew now" : "Apply for verification"}
            </ButtonLink>
          </div>
        </div>
      ))}
    </section>
  );
}
