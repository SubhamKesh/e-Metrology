import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { roleHome } from "@/lib/roleHome";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: { pathname: string } } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await login(email, password);
      const dest = location.state?.from?.pathname ?? roleHome(user.role);
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Sign in" subtitle="Access your MaapSetu dashboard.">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <TextInput
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextInput
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button type="submit" loading={loading} className="mt-2 w-full">
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-sm text-slate-500">
        New to MaapSetu?{" "}
        <Link to="/register" className="font-medium text-teal">
          Create an account
        </Link>
      </p>
      <p className="mt-8 text-xs text-slate-400">
        Have a certificate to check instead?{" "}
        <Link to="/verify" className="font-medium text-slate-500 underline">
          Verify a certificate
        </Link>
      </p>
    </AuthLayout>
  );
}
