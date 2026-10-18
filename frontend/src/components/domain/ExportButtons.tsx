import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { ReportsApi, type ReportFormat, type ReportKind } from "@/lib/endpoints";
import { saveBlob } from "@/lib/saveFile";

interface Props {
  kind: ReportKind;
  /** The filters currently applied to the list, so the file holds exactly what is on screen. */
  params?: object;
  disabled?: boolean;
}

// "Export CSV" / "Export PDF" for the list on screen. The file is built by the server from the same
// filters, limited to what this person may see.
export function ExportButtons({ kind, params, disabled }: Props) {
  const [busy, setBusy] = useState<ReportFormat | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  async function run(format: ReportFormat) {
    setBusy(format);
    setNotice(null);
    try {
      const file = await ReportsApi.download(kind, format, params);
      saveBlob(file.blob, file.filename);
      setNotice(
        file.truncated
          ? {
              tone: "error",
              text: `Saved the newest ${file.rows.toLocaleString("en-IN")} of ${file.total.toLocaleString("en-IN")} records. Narrow the filters to get the rest.`,
            }
          : { tone: "ok", text: `Saved ${file.rows.toLocaleString("en-IN")} record${file.rows === 1 ? "" : "s"}.` },
      );
    } catch (err) {
      setNotice({
        tone: "error",
        text: err instanceof ApiError ? err.message : "Couldn't create the report. Please try again.",
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1.5 sm:items-end">
      <div className="flex gap-2">
        <Button type="button" size="sm" variant="secondary" disabled={disabled || busy !== null} loading={busy === "csv"} onClick={() => run("csv")}>
          Export CSV
        </Button>
        <Button type="button" size="sm" variant="secondary" disabled={disabled || busy !== null} loading={busy === "pdf"} onClick={() => run("pdf")}>
          Export PDF
        </Button>
      </div>
      {notice && (
        <p role="status" className={`text-xs ${notice.tone === "error" ? "text-danger" : "text-slate-500"}`}>
          {notice.text}
        </p>
      )}
    </div>
  );
}
