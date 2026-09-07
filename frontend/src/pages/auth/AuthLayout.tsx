import type { ReactNode } from "react";

function BrandIdentity({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <svg
        viewBox="0 0 100 100"
        className={compact ? "h-8 w-8 shrink-0" : "h-10 w-10 shrink-0"}
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="auth-logo-ring" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#0d3a59" />
            <stop offset="100%" stopColor="#0d4d73" />
          </linearGradient>
        </defs>
        <circle cx="50" cy="50" r="44" fill="#f7f1e6" stroke="url(#auth-logo-ring)" strokeWidth="7" />
        <circle cx="50" cy="50" r="36" fill="none" stroke="#b88f4b" strokeWidth="3" opacity="0.9" />
        <g stroke="#b88f4b" strokeLinecap="round" strokeWidth="2.5">
          <path d="M25 36 L50 60 L75 36" fill="none" />
          <path d="M50 60 L50 33" fill="none" />
          <path d="M15 68 H85" stroke="#0d3a59" strokeWidth="4" />
          <path d="M20 76 L33 68 H67 L80 76" fill="none" stroke="#0d3a59" strokeWidth="4" />
        </g>
        <g fill="#0d3a59">
          <rect x="46" y="18" width="8" height="12" rx="2" />
          <path d="M50 10 L54 18 H46 Z" />
        </g>
        <path d="M50 18 L50 82" stroke="#0d3a59" strokeWidth="2" opacity="0.7" />
      </svg>
      <span className={compact ? "font-display text-xl text-ink" : "font-display text-xl text-paper"}>
        MaapSetu
      </span>
    </div>
  );
}

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <div className="hidden flex-col justify-between bg-ink px-12 py-10 text-paper md:flex">
        <BrandIdentity />
        <div className="max-w-sm">
          <p className="font-display text-3xl leading-snug">
            Every weighing and measuring instrument, verified and traceable.
          </p>
          <p className="mt-4 text-sm text-paper2/80">
            Legal Metrology verification for weighing and measuring instruments —
            from registration to certificate, in one system.
          </p>
        </div>
        <p className="text-xs text-paper2/50">Government of India · Legal Metrology</p>
      </div>
      <div className="flex flex-col justify-center px-6 py-12 sm:px-12 md:px-16">
        <div className="mx-auto w-full max-w-sm">
          <div className="md:hidden">
            <BrandIdentity compact />
          </div>
          <h1 className="mt-6 font-display text-2xl text-ink md:mt-0">{title}</h1>
          <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </div>
      </div>
    </div>
  );
}
