import type { ReactNode } from "react";
import { EmptyState, TableSkeleton } from "./States";

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  className?: string;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  isLoading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onRowClick?: (row: T) => void;
}

// Renders a real <table> at md+ and stacks each row into a small card below
// that, so dense operational tables stay legible on a phone in the field
// instead of forcing horizontal scroll.
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  isLoading,
  emptyTitle = "Nothing here yet",
  emptyDescription,
  onRowClick,
}: Props<T>) {
  if (isLoading) return <TableSkeleton cols={columns.length} />;
  if (rows.length === 0) return <EmptyState title={emptyTitle} description={emptyDescription} />;

  return (
    <>
      <table className="hidden w-full text-left text-sm md:table">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-slate-400">
            {columns.map((c, i) => (
              <th key={i} className={`px-4 py-2.5 font-medium ${c.className ?? ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={() => onRowClick?.(row)}
              className={onRowClick ? "cursor-pointer hover:bg-paper2/60" : ""}
            >
              {columns.map((c, i) => (
                <td key={i} className={`px-4 py-3 align-middle ${c.className ?? ""}`}>
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex flex-col gap-3 md:hidden">
        {rows.map((row) => (
          <div
            key={rowKey(row)}
            role={onRowClick ? "button" : undefined}
            tabIndex={onRowClick ? 0 : undefined}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            onKeyDown={
              onRowClick
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onRowClick(row);
                    }
                  }
                : undefined
            }
            className={`rounded-lg border border-line bg-white p-4 text-left shadow-panel ${
              onRowClick ? "cursor-pointer" : ""
            }`}
          >
            {columns.map((c, i) => (
              <div key={i} className="flex items-center justify-between gap-3 py-1 text-sm first:pt-0 last:pb-0">
                <span className="text-xs uppercase tracking-wide text-slate-400">{c.header}</span>
                <span className="text-right text-ink">{c.cell(row)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}