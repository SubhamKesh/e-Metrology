import { useGeoDistricts, useGeoStates } from "@/hooks/useData";
import type { Location } from "@/lib/types";

/** "Baharampur, Murshidabad, West Bengal" — falls back to raw codes until
 * the reference lookups resolve (both are cached per state, so this stays
 * cheap even across many table rows in the same state). */
export function LocationText({ location }: { location: Location }) {
  const { data: states } = useGeoStates();
  const { data: districts } = useGeoDistricts(location.state_code);
  const stateName = states?.find((s) => s.code === location.state_code)?.name ?? location.state_code;
  const districtName = districts?.find((d) => d.code === location.district_code)?.name ?? location.district_code;
  return (
    <span>
      {location.address_line}, {districtName}, {stateName}
    </span>
  );
}
