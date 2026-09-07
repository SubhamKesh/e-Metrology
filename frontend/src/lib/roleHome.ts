import type { Role } from "./types";

export function roleHome(role: Role): string {
  switch (role) {
    case "lmo":
      return `/app/lmo/queue`;
    case "gatc":
      return `/app/gatc/queue`;
    default:
      return `/app/${role}`;
  }
}
