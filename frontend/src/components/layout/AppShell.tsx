import { type ReactNode, useId, useState, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ROLE_NAV } from "@/lib/nav";
import { ROLE_LABEL } from "@/lib/types";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";
import { LogoutConfirmationDialog } from "@/components/ui/LogoutConfirmationDialog";
import { useApplications } from "@/hooks/useData";

function BrandButton({ onClick, className }: { onClick: () => void; className?: string }) {
  const brandId = useId();

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40 focus-visible:ring-offset-2",
        className,
      )}
      aria-label="Go to home page"
    >
      <svg viewBox="0 0 80 80" className="h-9 w-9 shrink-0 drop-shadow-sm" aria-hidden="true">
        <defs>
          <linearGradient id={`brandRing-${brandId}`} x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#0d3a59" />
            <stop offset="100%" stopColor="#0d4d73" />
          </linearGradient>
        </defs>
        <circle cx="40" cy="40" r="36" fill="#f7f3eb" stroke={`url(#brandRing-${brandId})`} strokeWidth="5" />
        <circle cx="40" cy="40" r="30" fill="none" stroke="#c9a15f" strokeWidth="2.5" opacity="0.9" />
        <g stroke="#b88f4b" strokeLinecap="round" strokeWidth="2.5">
          <path d="M21 26 L40 50 L59 26" fill="none" />
          <path d="M40 50 L40 27" fill="none" />
          <path d="M15 52 H65" stroke="#0d3a59" strokeWidth="3" />
          <path d="M18 58 L28 52 H52 L62 58" fill="none" stroke="#0d3a59" strokeWidth="3" />
          <path d="M25 62 H55" stroke="#c9a15f" strokeWidth="2.5" />
        </g>
        <g fill="#0d3a59">
          <rect x="36" y="18" width="8" height="10" rx="1.5" />
          <path d="M40 12 L42.8 18 H37.2 Z" />
        </g>
        <path d="M40 18 L40 62" stroke="#0d3a59" strokeWidth="1.5" opacity="0.7" />
      </svg>
      <span className="font-display text-[1.05rem] leading-none tracking-[-0.06em] text-ink sm:text-[1.15rem]">
        MaapSetu
      </span>
    </button>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [logoutDialogOpen, setLogoutDialogOpen] = useState(false);
  const [newIndicator, setNewIndicator] = useState(false);
  const [toast, setToast] = useState<{ id: string; text: string } | null>(null);
  const prevQueueRef = useRef<number | null>(null);

  const isOfficer = user?.role === "lmo" || user?.role === "gatc";
  const { data: queueData } = useApplications(isOfficer ? { status: "submitted", pollInterval: 5000 } : undefined);
  const queueCount = Array.isArray(queueData) ? queueData.length : 0;
  const qc = useQueryClient();

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    if (!isOfficer) return;
    const prev = prevQueueRef.current;
    if (prev !== null && queueCount > prev) {
      setNewIndicator(true);
      try {
        const AudioCtor =
          window.AudioContext ??
          (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (AudioCtor) {
          const ctx = new AudioCtor();
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = "sine";
          o.frequency.value = 880;
          o.connect(g);
          g.connect(ctx.destination);
          g.gain.value = 0.05;
          o.start();
          setTimeout(() => {
            o.stop();
            ctx.close();
          }, 180);
        }
      } catch {
        // ignore audio errors
      }

      const newestId = Array.isArray(queueData) && queueData.length ? queueData[0].id : null;
      if (newestId) setToast({ id: newestId, text: `New application ${newestId}` });

      const t = setTimeout(() => setNewIndicator(false), 3000);
      return () => clearTimeout(t);
    }
    prevQueueRef.current = queueCount;
  }, [queueCount, isOfficer, queueData]);

  useEffect(() => {
    if (!isOfficer || !user) return;
    const token = localStorage.getItem("maapsetu_token");
    if (!token) return;
    const loc = window.location;
    const protocol = loc.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${loc.host}/ws/notifications?token=${encodeURIComponent(token)}`;
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      return;
    }

    ws.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        if (payload?.type === "application_submitted") {
          const app = payload.application;
          setToast({ id: app.id, text: `New application ${app.id}` });
          setNewIndicator(true);
          setTimeout(() => setNewIndicator(false), 3000);
          try {
            qc.invalidateQueries({ queryKey: ["applications"] });
          } catch {
            // ignore invalidation issues
          }
          try {
            const AudioCtor =
              window.AudioContext ??
              (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
            if (AudioCtor) {
              const ctx = new AudioCtor();
              const o = ctx.createOscillator();
              const g = ctx.createGain();
              o.type = "sine";
              o.frequency.value = 880;
              o.connect(g);
              g.connect(ctx.destination);
              g.gain.value = 0.05;
              o.start();
              setTimeout(() => {
                o.stop();
                ctx.close();
              }, 180);
            }
          } catch {
            // ignore audio errors
          }
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      ws = null;
    };

    return () => {
      if (ws) ws.close();
    };
  }, [isOfficer, qc, user]);

  if (!user) return null;
  const nav = ROLE_NAV[user.role];

  const handleLogout = () => {
    setLogoutDialogOpen(false);
    logout();
    navigate("/login");
  };

  return (
    <div className="flex min-h-screen bg-paper">
      {/* Desktop nav rail */}
      <aside className="hidden w-60 flex-col border-r border-line bg-white md:flex">
        <div className="flex h-16 items-center gap-2 border-b border-line px-5">
          <BrandButton onClick={() => navigate(nav.base)} className="transition-colors hover:opacity-90" />
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
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => setLogoutDialogOpen(true)}>
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
          <BrandButton onClick={() => navigate(nav.base)} className="md:hidden" />
          <div className="hidden items-center gap-3 md:flex">
            <span className="rounded-sm bg-brass-50 px-2 py-0.5 text-xs font-medium text-brass-600">
              {ROLE_LABEL[user.role]}
            </span>
          </div>
          <div className="flex items-center gap-3">
            {user.role !== "owner" && (
              <Button size="sm" onClick={() => navigate(nav.primaryCta.to)} className="hidden sm:inline-flex">
                {nav.primaryCta.label}
                {isOfficer && (
                  <span
                    className={`ml-3 inline-flex items-center rounded-full bg-teal-600 px-2 py-0.5 text-xs font-semibold text-white ${
                      newIndicator ? "animate-pulse ring-2 ring-emerald-200" : ""
                    }`}
                  >
                    {queueCount}
                  </span>
                )}
                {newIndicator && (
                  <span className="ml-2 inline-block rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">New</span>
                )}
              </Button>
            )}
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-teal-50 text-sm font-medium text-teal-700">
              {user.name.slice(0, 1).toUpperCase()}
            </div>
          </div>
        </header>

        {/* Toast container */}
        {toast && (
          <div className="fixed right-4 top-20 z-50 max-w-sm animate-slide-in">
            <div className="rounded-md border border-line bg-white p-3 shadow-lg">
              <p className="text-sm font-medium text-ink">{toast.text}</p>
              <div className="mt-2 flex justify-end">
                <button
                  className="text-xs text-slate-500 hover:text-slate-700"
                  onClick={() => setToast(null)}
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        )}

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
              <BrandButton
                onClick={() => {
                  setMenuOpen(false);
                  navigate(nav.base);
                }}
                className=""
              />
              <button onClick={() => setMenuOpen(false)} aria-label="Close menu">✕</button>
            </div>
            <p className="mb-4 text-sm text-slate-500">{user.name} · {ROLE_LABEL[user.role]}</p>
            <Button
              variant="secondary"
              className="w-full"
              onClick={() => {
                setMenuOpen(false);
                setLogoutDialogOpen(true);
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      )}

      <LogoutConfirmationDialog
        open={logoutDialogOpen}
        onClose={() => setLogoutDialogOpen(false)}
        onConfirm={handleLogout}
      />
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
