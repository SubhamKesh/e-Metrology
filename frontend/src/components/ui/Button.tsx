import { type ButtonHTMLAttributes, forwardRef } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const variantClasses: Record<Variant, string> = {
  primary: "bg-teal text-white shadow-panel hover:bg-teal-600 active:bg-teal-700 disabled:bg-teal/50",
  secondary: "bg-white text-ink border border-line hover:bg-paper2 active:bg-paper2 disabled:text-slate-500",
  ghost: "bg-transparent text-slate-600 hover:bg-paper2",
  danger: "bg-danger text-white hover:bg-danger/90 disabled:bg-danger/50",
};

// Touch-friendly: 44px on phones for md/sm, compact on pointer devices.
const sizeClasses: Record<Size, string> = {
  sm: "h-10 px-3 text-sm sm:h-9",
  md: "h-11 px-4 text-sm sm:h-10",
  lg: "h-12 px-6 text-base",
};

const base =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40 focus-visible:ring-offset-2 disabled:cursor-not-allowed";

export function buttonClasses(variant: Variant = "primary", size: Size = "md", className?: string) {
  return cn(base, variantClasses[variant], sizeClasses[size], className);
}

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ className, variant = "primary", size = "md", loading, disabled, children, ...rest }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        className={buttonClasses(variant, size, className)}
        {...rest}
      >
        {loading && (
          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
        )}
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";

/** A router <Link> that looks like a Button — avoids invalid <a><button/></a> nesting. */
export function ButtonLink({
  variant = "primary",
  size = "md",
  className,
  ...rest
}: LinkProps & { variant?: Variant; size?: Size }) {
  return <Link className={buttonClasses(variant, size, className)} {...rest} />;
}
