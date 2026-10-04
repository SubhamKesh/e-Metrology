import { type ReactNode, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Brand } from "@/components/ui/Brand";
import { ButtonLink } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

/** Header + footer shared by every logged-out page (landing, verify). */
export function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:shadow-raised"
      >
        Skip to content
      </a>
      <PublicHeader />
      <main id="main" className="flex-1">
        {children}
      </main>
      <PublicFooter />
    </div>
  );
}

function PublicHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/95 backdrop-blur">
      <div className="container-page flex h-16 items-center justify-between gap-3">
        <Link to="/" aria-label="MaapSetu home" className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40">
          <Brand />
        </Link>

        {/* Desktop */}
        <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
          <a href="/#features" className="rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-paper2">Features</a>
          <Link to="/how-it-works" className="rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-paper2">How it works</Link>
          <Link to="/about" className="rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-paper2">About</Link>
          <NavLink
            to="/verify"
            className={({ isActive }) =>
              cn(
                "ml-2 inline-flex h-10 items-center rounded-md border border-teal px-4 text-sm font-medium text-teal hover:bg-teal-50",
                isActive && "bg-teal-50",
              )
            }
          >
            Verify a certificate
          </NavLink>
          <ButtonLink to="/login" variant="secondary" className="ml-1">Sign in</ButtonLink>
          <ButtonLink to="/register" className="ml-1">Get started</ButtonLink>
        </nav>

        {/* Mobile: Verify stays one tap away, everything else in the menu */}
        <div className="flex items-center gap-2 md:hidden">
          <ButtonLink to="/verify" variant="secondary" size="sm" className="border-teal text-teal">
            Verify
          </ButtonLink>
          <button
            type="button"
            className="flex h-10 w-10 items-center justify-center rounded-md text-xl hover:bg-paper2"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? "✕" : "☰"}
          </button>
        </div>
      </div>

      {open && (
        <nav aria-label="Mobile" className="border-t border-line bg-paper md:hidden">
          <div className="container-page flex flex-col gap-1 py-3">
            <a href="/#features" onClick={() => setOpen(false)} className="rounded-md px-3 py-3 text-sm font-medium text-ink hover:bg-paper2">Features</a>
            <Link to="/how-it-works" onClick={() => setOpen(false)} className="rounded-md px-3 py-3 text-sm font-medium text-ink hover:bg-paper2">How it works</Link>
            <Link to="/about" onClick={() => setOpen(false)} className="rounded-md px-3 py-3 text-sm font-medium text-ink hover:bg-paper2">About MaapSetu</Link>
            <Link to="/login" onClick={() => setOpen(false)} className="rounded-md px-3 py-3 text-sm font-medium text-ink hover:bg-paper2">Sign in</Link>
            <ButtonLink to="/register" className="mt-2 w-full" onClick={() => setOpen(false)}>Create an account</ButtonLink>
          </div>
        </nav>
      )}
    </header>
  );
}

function PublicFooter() {
  return (
    <footer className="border-t border-line bg-ink text-paper2">
      <div className="container-page grid gap-8 py-10 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr]">
        <div>
          <Brand tone="light" />
          <p className="mt-3 max-w-sm text-sm text-paper2/70">
            Digital verification and certification for weighing and measuring instruments — from registration to a
            publicly verifiable certificate.
          </p>
        </div>
        <nav aria-label="Platform" className="text-sm">
          <p className="font-medium text-paper">Platform</p>
          <ul className="mt-3 space-y-2 text-paper2/70">
            <li><Link className="hover:text-paper" to="/verify">Verify a certificate</Link></li>
            <li><Link className="hover:text-paper" to="/login">Sign in</Link></li>
            <li><Link className="hover:text-paper" to="/register">Create an account</Link></li>
          </ul>
        </nav>
        <nav aria-label="Learn more" className="text-sm">
          <p className="font-medium text-paper">Learn more</p>
          <ul className="mt-3 space-y-2 text-paper2/70">
            <li><a className="hover:text-paper" href="/#features">Features</a></li>
            <li><Link className="hover:text-paper" to="/how-it-works">How Legal Metrology verification works</Link></li>
            <li><Link className="hover:text-paper" to="/about">About MaapSetu</Link></li>
            <li><a className="hover:text-paper" href="/#trust">Security &amp; traceability</a></li>
          </ul>
        </nav>
      </div>
      <div className="border-t border-white/10">
        <p className="container-page py-4 text-xs text-paper2/60">© MaapSetu e-Metrology · Digital Legal Metrology verification in India</p>
      </div>
    </footer>
  );
}
