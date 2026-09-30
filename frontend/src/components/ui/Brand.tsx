import { cn } from "@/lib/cn";

/** MaapSetu mark + wordmark. One implementation for public, auth and app chrome. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={cn("h-9 w-9 shrink-0", className)} aria-hidden="true">
      <circle cx="50" cy="50" r="44" fill="#f7f1e6" stroke="#0d3a59" strokeWidth="7" />
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
  );
}

export function Brand({ tone = "dark", className }: { tone?: "dark" | "light"; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <BrandMark />
      <span className={cn("font-display text-xl leading-none", tone === "light" ? "text-paper" : "text-ink")}>
        MaapSetu
      </span>
    </span>
  );
}
