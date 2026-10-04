import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Brand } from "@/components/ui/Brand";

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      {/* Brand panel — desktop only */}
      <div className="hidden flex-col justify-between bg-ink px-10 py-10 text-paper lg:flex xl:px-16">
        <Link to="/" aria-label="MaapSetu home" className="w-fit rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-paper/60">
          <Brand tone="light" />
        </Link>
        <div className="max-w-md">
          <p className="font-display text-4xl leading-tight">
            Every weighing and measuring instrument, verified and traceable.
          </p>
          <p className="mt-5 text-base text-paper2/80">
            Legal Metrology verification for weighing and measuring instruments — from registration to certificate, in
            one system.
          </p>
        </div>
        <div className="flex items-center justify-between text-xs text-paper2/60">
          <span>Government of India · Legal Metrology</span>
          <Link to="/verify" className="underline underline-offset-2 hover:text-paper">
            Verify a certificate
          </Link>
        </div>
      </div>

      <div className="flex flex-col bg-paper px-5 py-6 sm:px-10 lg:px-16">
        <div className="lg:hidden">
          <Link to="/" aria-label="MaapSetu home" className="inline-flex rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40">
            <Brand />
          </Link>
        </div>
        <div className="flex flex-1 items-start justify-center py-8 sm:items-center lg:py-12">
          <div className="w-full max-w-md">
            <h1 className="font-display text-3xl text-ink">{title}</h1>
            <p className="mt-1.5 text-sm text-slate-600">{subtitle}</p>
            <div className="mt-8">{children}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
