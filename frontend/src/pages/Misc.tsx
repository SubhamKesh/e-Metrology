import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { roleHome } from "@/lib/roleHome";
import { Button } from "@/components/ui/Button";

function Centered({ title, description, to, cta }: { title: string; description: string; to: string; cta: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-paper px-6 text-center">
      <h1 className="font-display text-3xl text-ink">{title}</h1>
      <p className="max-w-sm text-sm text-slate-500">{description}</p>
      <Link to={to}>
        <Button className="mt-3">{cta}</Button>
      </Link>
    </div>
  );
}

export function Unauthorized() {
  const { user } = useAuth();
  return (
    <Centered
      title="You don't have access to this page"
      description="This section isn't available for your role."
      to={user ? roleHome(user.role) : "/login"}
      cta={user ? "Back to dashboard" : "Sign in"}
    />
  );
}

export function NotFound() {
  const { user } = useAuth();
  return (
    <Centered
      title="Page not found"
      description="That page doesn't exist, or has moved."
      to={user ? roleHome(user.role) : "/login"}
      cta={user ? "Back to dashboard" : "Sign in"}
    />
  );
}
