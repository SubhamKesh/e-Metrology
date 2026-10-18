import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";

interface Props {
  search: string;
  onSearch: (value: string) => void;
  searchLabel?: string;
  searchPlaceholder?: string;
  searchHint?: string;
  /** Extra controls (selects, dates) placed beside the search box. */
  children?: ReactNode;
  /** True when anything is filtered; shows the Clear button. */
  active: boolean;
  onClear: () => void;
  dateError?: string | null;
  /** Usually <ExportButtons />. */
  actions?: ReactNode;
}

// The search box, filter controls and export buttons that sit above a list.
export function FilterBar({
  search,
  onSearch,
  searchLabel = "Search",
  searchPlaceholder,
  searchHint,
  children,
  active,
  onClear,
  dateError,
  actions,
}: Props) {
  return (
    <div className="mb-4 rounded-xl border border-line bg-white p-4 shadow-panel">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2">
          <TextInput
            label={searchLabel}
            type="search"
            maxLength={100}
            placeholder={searchPlaceholder}
            hint={searchHint}
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            autoComplete="off"
          />
        </div>
        {children}
      </div>
      {dateError && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {dateError}
        </p>
      )}
      {(active || actions) && (
        <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            {active && (
              <Button type="button" size="sm" variant="ghost" onClick={onClear}>
                Clear search and filters
              </Button>
            )}
          </div>
          {actions}
        </div>
      )}
    </div>
  );
}
