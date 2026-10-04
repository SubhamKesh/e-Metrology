import { cn } from "@/lib/cn";

/**
 * MaapSetu mark + wordmark. One implementation for public, auth and app chrome.
 * The mark is the supplied logo (public/logo-mark.png, transparent background);
 * the full lock-up with the Hindi name and tagline is public/logo-full.png.
 */

/** Logo mark. On dark surfaces (`onDark`) it sits on a white chip so the navy artwork stays legible. */
export function BrandMark({ className, onDark = false }: { className?: string; onDark?: boolean }) {
  const img = (
    <img
      src="/logo-mark.png"
      alt=""
      width={376}
      height={372}
      decoding="async"
      draggable={false}
      className={cn("h-9 w-9 shrink-0 object-contain", !onDark && className)}
      aria-hidden="true"
    />
  );
  if (!onDark) return img;
  return (
    <span className={cn("inline-flex shrink-0 items-center justify-center rounded-xl bg-white p-1", className)}>
      {img}
    </span>
  );
}

/** "MaapSetu" in the logo's two colours (navy "Maap", green "Setu"). */
export function BrandWordmark({ tone = "dark", className }: { tone?: "dark" | "light"; className?: string }) {
  return (
    <span className={cn("font-display leading-none", className)}>
      <span className={tone === "light" ? "text-paper" : "text-brand-navy"}>Maap</span>
      <span className={tone === "light" ? "text-brand-green-light" : "text-brand-green"}>Setu</span>
    </span>
  );
}

export function Brand({ tone = "dark", className }: { tone?: "dark" | "light"; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <BrandMark onDark={tone === "light"} />
      <BrandWordmark tone={tone} className="text-xl" />
    </span>
  );
}
