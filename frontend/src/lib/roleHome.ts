import type { Role } from "./types";

export function roleHome(role: Role): string {
  return `/app/${role}`;
}
