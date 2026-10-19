import { useState } from "react";
import { cn } from "@/lib/cn";

/** The person's picture, or their first initial when they have none (or the picture fails to load). */
export function Avatar({
  name,
  src,
  className,
}: {
  name: string;
  src?: string | null;
  className?: string;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  const showImage = !!src && failed !== src;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-teal-50 font-medium text-teal-700",
        className ?? "h-9 w-9 text-sm",
      )}
    >
      {showImage ? (
        <img src={src} alt="" className="h-full w-full object-cover" onError={() => setFailed(src)} />
      ) : (
        name.slice(0, 1).toUpperCase()
      )}
    </span>
  );
}
