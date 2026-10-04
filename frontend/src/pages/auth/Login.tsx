import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { roleHome } from "@/lib/roleHome";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: { pathname: string }; passwordReset?: boolean } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [emailError, setEmailError] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function handleEmailChange(value: string) {
    setEmail(value);
    if (emailError && EMAIL_REGEX.test(value)) {
      setEmailError(undefined);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!EMAIL_REGEX.test(email)) {
      setEmailError("Enter a valid email address.");
      return;
    }
    setEmailError(undefined);

    setLoading(true);
    try {
      const result = await login(email, password, rememberMe);
      if (result.kind === "mfa") {
        // Officer/admin accounts: password accepted, now the second step.
        navigate("/two-step", {
          replace: true,
          state: { mfaToken: result.mfaToken, setup: result.setup, email, from: location.state?.from },
        });
        return;
      }
      const dest = location.state?.from?.pathname ?? roleHome(result.user.role);
      navigate(dest, { replace: true });
    } catch (err) {
      // The backend answers 403 for accounts that can't sign in yet. Send
      // those users to the pending page instead of a bare error line.
      if (err instanceof ApiError && err.status === 403) {
        const msg = err.message.toLowerCase();
        if (msg.includes("awaiting admin approval")) {
          navigate("/pending", { state: { email, status: "pending" } });
          return;
        }
        if (msg.includes("not approved")) {
          navigate("/pending", { state: { email, status: "rejected" } });
          return;
        }
      }
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Sign in" subtitle="Access your MaapSetu dashboard.">
      {location.state?.passwordReset && (
        <p role="status" className="mb-4 rounded-md bg-success-50 px-3 py-2 text-sm text-success">
          Your password has been updated. Sign in with your new password.
        </p>
      )}
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <TextInput
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => handleEmailChange(e.target.value)}
          error={emailError}
        />
        <div className="relative">
          <TextInput
            label="Password"
            type={passwordVisible ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="pr-12"
          />
          <button
            type="button"
            onClick={() => setPasswordVisible((visible) => !visible)}
            aria-label={passwordVisible ? "Hide password" : "Show password"}
            aria-pressed={passwordVisible}
            className="absolute right-1 top-[1.625rem] flex h-11 w-11 items-center justify-center rounded-md text-slate-500 hover:bg-paper2 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/50 sm:h-10 sm:w-10"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-5 w-5"
            >
              {passwordVisible ? (
                <>
                  <path d="M3 3l18 18" />
                  <path d="M10.6 10.6a2 2 0 002.8 2.8" />
                  <path d="M9.9 5.2A10.8 10.8 0 0112 5c5 0 8.3 4.5 9 7-.3 1.1-1.2 2.5-2.5 3.7" />
                  <path d="M6.2 6.2C3.9 7.7 2.5 10 2 12c.7 2.5 4 7 10 7 1 0 2-.2 2.9-.5" />
                </>
              ) : (
                <>
                  <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" />
                  <circle cx="12" cy="12" r="3" />
                </>
              )}
            </svg>
          </button>
        </div>
        <div className="flex items-center justify-between gap-3">
          <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="h-4 w-4 rounded border-line accent-teal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal/40"
            />
            Remember me
          </label>
          <Link to="/forgot-password" className="text-sm font-medium text-teal underline underline-offset-2">
            Forgot password?
          </Link>
        </div>
        <p className="-mt-2 text-xs text-slate-500">
          "Remember me" keeps business accounts signed in for 30 days. It isn't available for officer or administrator
          accounts, which also need a code from an authenticator app at every sign-in. Don't use it on a shared
          computer.
        </p>
        {error && (
          <p role="alert" className="rounded-md bg-danger-50 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
        <Button type="submit" loading={loading} className="mt-2 w-full">
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-sm text-slate-500">
        New to MaapSetu?{" "}
        <Link to="/register" className="font-medium text-teal underline underline-offset-2">
          Create an account
        </Link>
      </p>
      <p className="mt-8 border-t border-line pt-5 text-sm text-slate-600">
        Have a certificate to check instead?{" "}
        <Link to="/verify" className="font-medium text-teal underline underline-offset-2">
          Verify a certificate
        </Link>
      </p>
    </AuthLayout>
  );
}
