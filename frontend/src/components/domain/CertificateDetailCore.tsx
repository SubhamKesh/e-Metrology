import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { CertificateApi } from "@/lib/endpoints";
import { Panel } from "@/components/ui/Card";
import { Badge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/Button";
import type { Certificate } from "@/lib/types";

export function CertificateDetailCore({ certificate }: { certificate: Certificate }) {
  const verifyUrl = `${window.location.origin}/verify/${certificate.id}`;
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // PDF held by the API (external storage was unavailable when it was issued):
  // fetch it with the auth header and open it, since a plain <a href> can't send it.
  async function openStoredPdf() {
    setDownloading(true);
    setDownloadError(null);
    try {
      const blob = await CertificateApi.pdf(certificate.id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setDownloadError("Couldn't download the PDF. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <Panel className="overflow-hidden">
        <div className="border-b border-line bg-paper2/40 px-6 py-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Certificate</p>
              <p className="font-mono text-sm text-ink">{certificate.cert_no ?? certificate.id}</p>
            </div>
            <Badge tone={certificate.is_expired ? "danger" : "success"}>
              {certificate.is_expired ? "Expired" : "Valid"}
            </Badge>
          </div>
        </div>
        <div className="grid gap-6 p-6 sm:grid-cols-[1fr_auto]">
          <dl className="grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
            {certificate.instrument && (
              <>
                <Field label="Instrument" value={certificate.instrument.type ?? "-"} />
                <Field label="UIID" value={certificate.instrument.uiid ?? "-"} />
                <Field
                  label="Make / model"
                  value={[certificate.instrument.manufacturer, certificate.instrument.model].filter(Boolean).join(" ") || "-"}
                />
                <Field label="Location" value={certificate.instrument.location ?? "-"} />
              </>
            )}
            <Field
              label="Verified on"
              value={new Date(certificate.verified_on).toLocaleDateString("en-IN", { dateStyle: "long" })}
            />
            <Field
              label="Valid until"
              value={new Date(certificate.valid_until).toLocaleDateString("en-IN", { dateStyle: "long" })}
            />
          </dl>
          <div className="flex flex-col items-center gap-2 justify-self-center">
            <div className="rounded-md border border-line bg-white p-3">
              <QRCodeSVG value={verifyUrl} size={112} />
            </div>
            <p className="text-center text-xs text-slate-500">Scan to verify</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3 border-t border-line px-6 py-4">
          {certificate.pdf_url ? (
            <a href={certificate.pdf_url} target="_blank" rel="noreferrer">
              <Button size="sm">Download PDF</Button>
            </a>
          ) : certificate.has_pdf ? (
            <Button size="sm" loading={downloading} onClick={openStoredPdf}>
              Download PDF
            </Button>
          ) : (
            <Button size="sm" disabled>
              PDF not available
            </Button>
          )}
          <a href={verifyUrl} target="_blank" rel="noreferrer">
            <Button size="sm" variant="secondary">
              Open public verification page
            </Button>
          </a>
        </div>
        {downloadError && <p className="px-6 pb-4 text-sm text-danger">{downloadError}</p>}
      </Panel>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-ink">{value}</dd>
    </div>
  );
}
