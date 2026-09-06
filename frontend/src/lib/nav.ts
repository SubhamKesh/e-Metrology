import type { Role } from "./types";

export interface NavItem {
  label: string;
  to: string;
  end?: boolean;
}

export interface RoleNav {
  base: string;
  primaryCta: { label: string; to: string };
  items: NavItem[];
}

export const ROLE_NAV: Record<Role, RoleNav> = {
  owner: {
    base: "/app/owner",
    primaryCta: { label: "Register instrument", to: "/app/owner/instruments/new" },
    items: [
      { label: "Overview", to: "/app/owner", end: true },
      { label: "My instruments", to: "/app/owner/instruments" },
      { label: "Applications", to: "/app/owner/applications" },
      { label: "Certificates", to: "/app/owner/certificates" },
    ],
  },
  gatc: {
    base: "/app/gatc",
    primaryCta: { label: "Verification queue", to: "/app/gatc/queue" },
    items: [
      { label: "Overview", to: "/app/gatc", end: true },
      { label: "Queue", to: "/app/gatc/queue" },
      { label: "My assignments", to: "/app/gatc/assignments" },
      { label: "Certificates", to: "/app/gatc/certificates" },
    ],
  },
  lmo: {
    base: "/app/lmo",
    primaryCta: { label: "Verification queue", to: "/app/lmo/queue" },
    items: [
      { label: "Overview", to: "/app/lmo", end: true },
      { label: "Queue", to: "/app/lmo/queue" },
      { label: "My assignments", to: "/app/lmo/assignments" },
      { label: "Certificates", to: "/app/lmo/certificates" },
    ],
  },
  admin: {
    base: "/app/admin",
    primaryCta: { label: "All applications", to: "/app/admin/applications" },
    items: [
      { label: "Overview", to: "/app/admin", end: true },
      { label: "Instruments", to: "/app/admin/instruments" },
      { label: "Applications", to: "/app/admin/applications" },
      { label: "Certificates", to: "/app/admin/certificates" },
    ],
  },
};
