import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useVerifyCertificate } from "@/hooks/useData";
import { TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/States";
import { ApiError } from "@/lib/api";

export default function VerifyCertificate() {
  const { certId } = useParams();
  const navigate = useNavigate();
  const [manualId, setManualId] = useState("");
  const { data, isLoading, isError, error } = useVerifyCertificate(certId);

  if (!certId) {
    return (
      <Shell>
        <h1 className="font-display text-2xl text-ink">Verify a certificate</h1>
        <p className="mt-2 text-sm text-slate-500">
          Scan the QR code on the instrument, or enter the certificate ID printed on it.
        </p>
        <form
          className="mt-6 flex flex-col gap-3 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (manualId.trim()) navigate(`/verify/${encodeURIComponent(manualId.trim())}`);
          }}
        >
          <TextInput
            label="Certificate ID"
            value={manualId}
            onChange={(e) => setManualId(e.target.value)}
            placeholder="e.g. LM-CERT-2026-91827"
            className="flex-1"
          />
          <Button type="submit" className="sm:self-end">
            Check certificate
          </Button>
        </form>
      </Shell>
    );
  }

  if (isLoading) {
    return (
      <Shell>
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="mt-4 h-4 w-1/2" />
        <Skeleton className="mt-8 h-40 w-full" />
      </Shell>
    );
  }

  if (isError) {
    return (
      <Shell>
        <StatusHeader tone="danger" title="Couldn't check this certificate" />
        <p className="mt-2 text-sm text-slate-500">
          {error instanceof ApiError ? error.message : "Please try again in a moment."}
        </p>
      </Shell>
    );
  }

  if (!data?.valid) {
    return (
      <Shell>
        <StatusHeader tone="danger" title="Not found" />
        <p className="mt-2 text-sm text-slate-500">
          No certificate matches ID <span className="font-mono">{certId}</span>. Double-check the ID, or the
          certificate may not have been issued.
        </p>
      </Shell>
    );
  }

  const { certificate, instrument, owner } = data;
  const isExpired = certificate?.is_expired;

  return (
    <Shell>
      <StatusHeader
        tone={isExpired ? "warning" : "success"}
        title={isExpired ? "Certificate expired" : "Authentic certificate"}
      />
      <div className="mt-6 divide-y divide-line rounded-lg border border-line bg-white">
        <Row label="Instrument" value={instrument?.type} />
        <Row label="Manufacturer" value={instrument?.manufacturer} />
        <Row label="Model" value={instrument?.model} />
        <Row label="UIID" value={instrument?.uiid} className="font-mono" />
        <Row label="Owner" value={owner?.org_name} />
        <Row label="Location" value={owner?.location} />
        <Row
          label="Verified on"
          value={certificate ? new Date(certificate.verified_on).toLocaleDateString("en-IN", { dateStyle: "long" }) : "—"}
        />
        <Row
          label="Valid until"
          value={certificate ? new Date(certificate.valid_until).toLocaleDateString("en-IN", { dateStyle: "long" }) : "—"}
        />
        <Row label="Certificate ID" value={certificate?.id} className="font-mono text-xs" />
      </div>
      <p className="mt-6 text-xs text-slate-400">
        This result is generated live from the MaapSetu verification registry.
      </p>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen justify-center bg-paper2 px-4 py-10 sm:py-16">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <span className="font-display text-lg text-ink">MaapSetu</span>
          <p className="text-xs uppercase tracking-wide text-slate-400">Legal Metrology Verification</p>
        </div>
        <div className="rounded-xl border border-line bg-paper p-6 shadow-raised sm:p-8">{children}</div>
      </div>
    </div>
  );
}

function StatusHeader({ tone, title }: { tone: "success" | "warning" | "danger"; title: string }) {
  const iconTone = {
    success: "bg-success-50 text-success",
    warning: "bg-warning-50 text-warning",
    danger: "bg-danger-50 text-danger",
  }[tone];
  const symbol = tone === "success" ? "✓" : tone === "warning" ? "!" : "✕";
  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <div className={`flex h-12 w-12 items-center justify-center rounded-full text-xl ${iconTone}`}>{symbol}</div>
      <h1 className="font-display text-2xl text-ink">{title}</h1>
    </div>
  );
}

function Row({ label, value, className }: { label: string; value?: string; className?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
      <span className="text-slate-400">{label}</span>
      <span className={`text-right text-ink ${className ?? ""}`}>{value ?? "—"}</span>
    </div>
  );
}
