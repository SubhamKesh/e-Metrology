import type { ReactNode } from "react";

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <div className="hidden flex-col justify-between bg-ink px-12 py-10 text-paper md:flex">
        <span className="font-display text-xl">MaapSetu</span>
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
          <span className="font-display text-xl text-ink md:hidden">MaapSetu</span>
          <h1 className="mt-6 font-display text-2xl text-ink md:mt-0">{title}</h1>
          <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </div>
      </div>
    </div>
  );
}
