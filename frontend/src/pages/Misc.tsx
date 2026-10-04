import { useAuth } from "@/context/AuthContext";
import { roleHome } from "@/lib/roleHome";
import { ButtonLink } from "@/components/ui/Button";
import { Seo } from "@/seo/Seo";
import type { SeoRouteKey } from "@/seo/seoConfig";

function Centered({
  seo,
  title,
  description,
  to,
  cta,
}: {
  seo: SeoRouteKey;
  title: string;
  description: string;
  to: string;
  cta: string;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-paper px-6 text-center">
      <Seo route={seo} />
      <h1 className="font-display text-3xl text-ink">{title}</h1>
      <p className="max-w-sm text-sm text-slate-500">{description}</p>
      <ButtonLink to={to} className="mt-3">
        {cta}
      </ButtonLink>
    </div>
  );
}

export function Unauthorized() {
  const { user } = useAuth();
  return (
    <Centered
      seo="/unauthorized"
      title="You don't have access to this page"
      description="This section isn't available for your role."
      to={user ? roleHome(user.role) : "/"}
      cta={user ? "Back to dashboard" : "Go to home page"}
    />
  );
}

export function NotFound() {
  const { user } = useAuth();
  return (
    <Centered
      seo="notFound"
      title="Page not found"
      description="That page doesn't exist, or has moved."
      to={user ? roleHome(user.role) : "/"}
      cta={user ? "Back to dashboard" : "Go to home page"}
    />
  );
}
