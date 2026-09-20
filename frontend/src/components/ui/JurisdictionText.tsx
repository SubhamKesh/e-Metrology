import { useGeoDistricts, useGeoStates } from "@/hooks/useData";
import type { Jurisdiction } from "@/lib/types";

export function JurisdictionText({ jurisdiction }: { jurisdiction: Jurisdiction | null }) {
  const { data: states } = useGeoStates();
  const { data: districts } = useGeoDistricts(jurisdiction?.state_code);

  if (!jurisdiction) return <span className="text-slate-400">National (no jurisdiction)</span>;

  const stateName = states?.find((s) => s.code === jurisdiction.state_code)?.name ?? jurisdiction.state_code;
  if (!jurisdiction.district_code) return <span>{stateName} (state-level)</span>;

  const districtName = districts?.find((d) => d.code === jurisdiction.district_code)?.name ?? jurisdiction.district_code;
  return (
    <span>
      {districtName}, {stateName}
    </span>
  );
}
