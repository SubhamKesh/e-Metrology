import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { AuthApi } from "@/lib/endpoints";
import { isValidEmail, isValidPassword, PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, PASSWORD_POLICY_ERROR } from "@/lib/validation";
import { PasswordRequirements } from "@/components/ui/PasswordRequirements";
// Matches PASSWORD_RESET_COOLDOWN_SECONDS on the backend: a resend inside this
// window would be silently ignored server-side, so the button waits it out.
const RESEND_COOLDOWN_SECONDS = 60;

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [step, setStep] = useState<"email" | "reset">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  async function sendCode(): Promise<boolean> {
    setError(null);
    setNotice(null);
    if (!isValidEmail(email)) {
      setError("Enter a valid email address.");
      return false;
    }
    setLoading(true);
    try {
      // The API answers the same way whether or not an account exists, so the
      // wording below must not promise that one does.
      await AuthApi.forgotPassword({ email: email.trim() });
      setCooldown(RESEND_COOLDOWN_SECONDS);
      setNotice(`If an account exists for ${email.trim()}, we've sent a 6-digit code. It expires in 10 minutes.`);
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send the code. Try again.");
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function onSendCode(e: FormEvent) {
    e.preventDefault();
    if (await sendCode()) setStep("reset");
  }

  async function onResend() {
    await sendCode();
  }

  async function onReset(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (code.length !== 6) {
      setError("Enter the 6-digit code from your email.");
      return;
    }
    if (!isValidPassword(newPassword)) {
      setError(PASSWORD_POLICY_ERROR);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The two passwords don't match.");
      return;
    }

    setLoading(true);
    try {
      await AuthApi.resetPassword({ email: email.trim(), code, new_password: newPassword });
      navigate("/login", { replace: true, state: { passwordReset: true } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout seo="/forgot-password"
      title="Reset your password"
      subtitle={
        step === "email"
          ? "Enter your account email and we'll send you a verification code."
          : "Enter the code we emailed you and choose a new password."
      }
    >
      {step === "email" ? (
        <form onSubmit={onSendCode} className="flex flex-col gap-4">
          <TextInput
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {error && (
            <p role="alert" className="rounded-md bg-danger-50 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}
          <Button type="submit" loading={loading} className="mt-2 w-full">
            Send reset code
          </Button>
          <p className="text-xs text-slate-500">
            Legal Metrology Officer, GATC and administrator accounts can't reset their password here — contact your
            department administrator.
          </p>
        </form>
      ) : (
        <form onSubmit={onReset} className="flex flex-col gap-4">
          {notice && (
            <p role="status" className="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-700">
              {notice}
            </p>
          )}
          <TextInput
            label="6-digit code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          />
          <TextInput
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            minLength={PASSWORD_MIN_LENGTH}
            maxLength={PASSWORD_MAX_LENGTH}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <PasswordRequirements password={newPassword} />
          <TextInput
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            required
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
          {error && (
            <p role="alert" className="rounded-md bg-danger-50 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}
          <Button type="submit" loading={loading} className="mt-2 w-full">
            Reset password
          </Button>
          <div className="flex items-center justify-between text-sm">
            <button
              type="button"
              onClick={onResend}
              disabled={loading || cooldown > 0}
              className="font-medium text-teal underline underline-offset-2 disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline"
            >
              {cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
            </button>
            <button
              type="button"
              onClick={() => {
                setStep("email");
                setCode("");
                setError(null);
                setNotice(null);
              }}
              className="text-slate-600 underline underline-offset-2"
            >
              Use a different email
            </button>
          </div>
        </form>
      )}
      <p className="mt-6 text-sm text-slate-500">
        Remembered it?{" "}
        <Link to="/login" className="font-medium text-teal underline underline-offset-2">
          Back to sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
