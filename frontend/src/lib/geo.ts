export interface GpsFix {
  lat: number;
  lng: number;
  accuracy_m: number;
}

/** One-shot GPS fix. Resolves null if unavailable, denied or timed out (never throws). */
export function getGpsFix(timeoutMs = 10000): Promise<GpsFix | null> {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy_m: Math.round(p.coords.accuracy) }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 30000 },
    );
  });
}
