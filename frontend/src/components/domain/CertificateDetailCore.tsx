import { QRCodeSVG } from "qrcode.react";
import { Panel } from "@/components/ui/Card";
import { Badge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/Button";
import type { Certificate } from "@/lib/types";

export function CertificateDetailCore({ certificate }: { certificate: Certificate }) {
  const verifyUrl = `${window.location.origin}/verify/${certificate.id}`;

  return (
    <div className="max-w-2xl">
      <Panel className="overflow-hidden">
        <div className="border-b border-line bg-paper2/40 px-6 py-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-400">Certificate</p>
              <p className="font-mono text-sm text-ink">{certificate.id}</p>
            </div>
            <Badge tone={certificate.is_expired ? "danger" : "success"}>
              {certificate.is_expired ? "Expired" : "Valid"}
            </Badge>
          </div>
        </div>
        <div className="grid gap-6 p-6 sm:grid-cols-[1fr_auto]">
          <dl className="grid grid-cols-2 gap-y-4 text-sm">
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
            <p className="text-center text-xs text-slate-400">Scan to verify</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3 border-t border-line px-6 py-4">
          <a href={certificate.pdf_url} target="_blank" rel="noreferrer">
            <Button size="sm">Download PDF</Button>
          </a>
          <a href={verifyUrl} target="_blank" rel="noreferrer">
            <Button size="sm" variant="secondary">
              Open public verification page
            </Button>
          </a>
        </div>
      </Panel>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-ink">{value}</dd>
    </div>
  );
}
