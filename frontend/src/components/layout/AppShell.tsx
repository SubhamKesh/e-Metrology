import { type ReactNode, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ROLE_NAV } from "@/lib/nav";
import { ROLE_LABEL } from "@/lib/types";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  if (!user) return null;
  const nav = ROLE_NAV[user.role];

  return (
    <div className="flex min-h-screen bg-paper">
      {/* Desktop nav rail */}
      <aside className="hidden w-60 flex-col border-r border-line bg-white md:flex">
        <div className="flex h-16 items-center gap-2 border-b border-line px-5">
          <span className="font-display text-lg text-ink">MaapSetu</span>
        </div>
        <nav className="flex-1 space-y-0.5 px-3 py-4">
          {nav.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "block rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-teal-50 text-teal-700" : "text-slate-600 hover:bg-paper2",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-line p-3">
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => { logout(); navigate("/login"); }}>
            Sign out
          </Button>
        </div>
      </aside>

      <div className="flex min-h-screen flex-1 flex-col">
        {/* Topbar */}
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-line bg-white/90 px-4 backdrop-blur md:px-6">
          <button className="text-lg md:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            ☰
          </button>
          <span className="font-display text-lg text-ink md:hidden">MaapSetu</span>
          <div className="hidden items-center gap-3 md:flex">
            <span className="rounded-sm bg-brass-50 px-2 py-0.5 text-xs font-medium text-brass-600">
              {ROLE_LABEL[user.role]}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Button size="sm" onClick={() => navigate(nav.primaryCta.to)} className="hidden sm:inline-flex">
              {nav.primaryCta.label}
            </Button>
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-teal-50 text-sm font-medium text-teal-700">
              {user.name.slice(0, 1).toUpperCase()}
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 pb-24 md:px-8 md:py-8 md:pb-8">{children}</main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-white md:hidden">
        {nav.items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium",
                isActive ? "text-teal" : "text-slate-400",
              )
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Mobile menu drawer */}
      {menuOpen && (
        <div className="fixed inset-0 z-30 md:hidden">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setMenuOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 bg-white p-5">
            <div className="mb-6 flex items-center justify-between">
              <span className="font-display text-lg">MaapSetu</span>
              <button onClick={() => setMenuOpen(false)} aria-label="Close menu">✕</button>
            </div>
            <p className="mb-4 text-sm text-slate-500">{user.name} · {ROLE_LABEL[user.role]}</p>
            <Button
              variant="secondary"
              className="w-full"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="font-display text-2xl text-ink">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {action}
    </div>
  );
}
