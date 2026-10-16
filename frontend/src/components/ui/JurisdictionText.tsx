import { useGeoDistricts, useGeoStates } from "@/hooks/useData";
import type { Jurisdiction, Role } from "@/lib/types";
import { Badge } from "@/components/ui/StatusBadge";

/**
 * How an officer's scope reads in the UI.
 *  - LMO  = district-level  -> "Kolkata district" / "West Bengal"
 *  - GATC = state-level     -> "West Bengal" / "Whole state"
 * An LMO with no district (older accounts) is flagged, because the backend
 * gives such an account no access until a district is assigned.
 */
export function JurisdictionText({ jurisdiction, role }: { jurisdiction: Jurisdiction | null; role?: Role }) {
  const { data: states } = useGeoStates();
  const { data: districts } = useGeoDistricts(jurisdiction?.state_code);

  if (!jurisdiction) return <span className="text-slate-500">National (no jurisdiction)</span>;

  const stateName = states?.find((s) => s.code === jurisdiction.state_code)?.name ?? jurisdiction.state_code;

  if (!jurisdiction.district_code) {
    if (role === "lmo") {
      return (
        <div className="flex flex-col items-start gap-1">
          <Badge tone="warning">District not assigned</Badge>
          <span className="text-xs text-slate-500">{stateName}</span>
        </div>
      );
    }
    return (
      <div className="leading-tight">
        <p className="text-ink">{stateName}</p>
        <p className="text-xs text-slate-500">Whole state</p>
      </div>
    );
  }

  const districtName = districts?.find((d) => d.code === jurisdiction.district_code)?.name ?? jurisdiction.district_code;
  return (
    <div className="leading-tight">
      <p className="text-ink">{districtName}</p>
      <p className="text-xs text-slate-500">District · {stateName}</p>
    </div>
  );
}
