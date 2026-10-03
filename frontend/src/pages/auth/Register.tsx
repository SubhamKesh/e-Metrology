import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import { roleHome } from "@/lib/roleHome";
import type { Role } from "@/lib/types";
import { isValidName, isValidEmail, isValidPhone, isValidPassword, PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, PASSWORD_POLICY_ERROR } from "@/lib/validation";
import { PasswordRequirements } from "@/components/ui/PasswordRequirements";

// Self-registration is for owner (business/user) accounts only. lmo/gatc
// are real government officer roles and are invite-only — an admin
// creates those accounts directly (see AdminUsers.tsx / POST
// /admin/users/create-officer). There is deliberately no role picker
// here anymore.
const OWNER_ROLE: Role = "owner";

type FieldErrors = {
  name?: string;
  email?: string;
  contact?: string;
};

type OtpState = {
  sent: boolean;
  code: string;
  verified: boolean;
  sending: boolean;
  verifying: boolean;
  error: string | null;
};

const EMPTY_OTP_STATE: OtpState = {
  sent: false,
  code: "",
  verified: false,
  sending: false,
  verifying: false,
  error: null,
};

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    org_name: "",
    contact: "",
  });
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Email OTP is the only verification. POST /auth/register enforces it
  // server-side too; this just lets the "Create account" button reflect
  // it before submitting.
  const [otp, setOtp] = useState<OtpState>({ ...EMPTY_OTP_STATE });
  const canCreateAccount = otp.verified;

  function updateOtp(patch: Partial<OtpState>) {
    setOtp((s) => ({ ...s, ...patch }));
  }

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function validateName(value: string): string | undefined {
    if (!value) return undefined;
    if (!isValidName(value)) return "Only letters and spaces are allowed.";
    return undefined;
  }

  function validateEmail(value: string): string | undefined {
    if (!value) return undefined;
    if (!isValidEmail(value)) return "Enter a valid email address.";
    return undefined;
  }

  function handleNameChange(value: string) {
    set("name", value);
    setFieldErrors((f) => ({ ...f, name: validateName(value) }));
  }

  function handleEmailChange(value: string) {
    set("email", value);
    setFieldErrors((f) => ({ ...f, email: validateEmail(value) }));
    // Changing the email after a code was sent/verified invalidates that
    // progress — the code was sent to the old address.
    if (otp.sent || otp.verified) {
      updateOtp({ ...EMPTY_OTP_STATE });
    }
  }

  function handleContactChange(value: string) {
    const digitsOnly = value.replace(/\D/g, "").slice(0, 10);
    set("contact", digitsOnly);
    setFieldErrors((f) => ({
      ...f,
      contact: digitsOnly.length > 0 && !isValidPhone(digitsOnly) ? "Invalid contact number." : undefined,
    }));
  }

  function validateAllOnSubmit(): boolean {
    const nameError = !isValidName(form.name) ? "Only letters and spaces are allowed." : undefined;
    const emailError = !isValidEmail(form.email) ? "Enter a valid email address." : undefined;
    const contactError =
      form.contact.length > 0 && !isValidPhone(form.contact) ? "Invalid contact number." : undefined;

    const errors: FieldErrors = { name: nameError, email: emailError, contact: contactError };
    setFieldErrors(errors);

    if (!isValidPassword(form.password)) {
      setError(PASSWORD_POLICY_ERROR);
      return false;
    }

    return !nameError && !emailError && !contactError;
  }

  async function sendCode() {
    if (!isValidEmail(form.email)) {
      updateOtp({ error: "Enter a valid email address first." });
      return;
    }
    updateOtp({ sending: true, error: null });
    try {
      await api.post("/otp/send", { channel: "email", identifier: form.email }, { public: true });
      updateOtp({ sending: false, sent: true, code: "" });
    } catch (err) {
      updateOtp({
        sending: false,
        error: err instanceof ApiError ? err.message : "Couldn't send the code. Try again.",
      });
    }
  }

  async function verifyCode() {
    if (otp.code.length !== 6) {
      updateOtp({ error: "Enter the 6-digit code." });
      return;
    }
    updateOtp({ verifying: true, error: null });
    try {
      await api.post(
        "/otp/verify",
        { channel: "email", identifier: form.email, code: otp.code },
        { public: true },
      );
      updateOtp({ verifying: false, verified: true, error: null });
    } catch (err) {
      updateOtp({
        verifying: false,
        error: err instanceof ApiError ? err.message : "Couldn't verify that code.",
      });
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!validateAllOnSubmit()) {
      return;
    }
    if (!canCreateAccount) {
      setError("Please verify your email before creating an account.");
      return;
    }

    setLoading(true);
    try {
      const user = await register({
        name: form.name,
        email: form.email,
        password: form.password,
        role: OWNER_ROLE,
        org_type: null,
        org_name: form.org_name || undefined,
        contact: form.contact || undefined,
      });
      navigate(roleHome(user.role), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Create your account" subtitle="Register instruments, track applications, and manage verifications.">
      <p className="mb-4 text-sm text-slate-500">
        This form is for business/owner accounts. Legal Metrology Officer and GATC accounts are created by an
        administrator and are not open for self-registration.
      </p>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <TextInput
          label="Full name"
          required
          value={form.name}
          onChange={(e) => handleNameChange(e.target.value)}
          error={fieldErrors.name}
        />
        <TextInput
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={form.email}
          onChange={(e) => handleEmailChange(e.target.value)}
          error={fieldErrors.email}
        />
        <TextInput
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          minLength={PASSWORD_MIN_LENGTH}
          maxLength={PASSWORD_MAX_LENGTH}
          value={form.password}
          onChange={(e) => set("password", e.target.value)}
        />
        <PasswordRequirements password={form.password} />
        <TextInput
          label="Business name"
          required
          value={form.org_name}
          onChange={(e) => set("org_name", e.target.value)}
        />
        <TextInput
          label="Contact number"
          type="tel"
          inputMode="numeric"
          value={form.contact}
          onChange={(e) => handleContactChange(e.target.value)}
          error={fieldErrors.contact}
        />

        <div className="rounded-md border border-line bg-paper2/40 p-4">
          <p className="text-sm font-medium text-ink">Verify your email</p>
          <p className="mt-1 text-xs text-slate-500">
            We'll send a 6-digit code to your email to confirm it's yours before creating your account.
          </p>

          <div className="mt-3">
            {otp.verified ? (
              <p className="text-sm text-teal">✓ Email verified.</p>
            ) : !otp.sent ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                loading={otp.sending}
                disabled={!isValidEmail(form.email)}
                onClick={sendCode}
              >
                Send code to email
              </Button>
            ) : (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <TextInput
                  label="6-digit code"
                  inputMode="numeric"
                  value={otp.code}
                  onChange={(e) => updateOtp({ code: e.target.value.replace(/\D/g, "").slice(0, 6) })}
                />
                <Button type="button" size="sm" loading={otp.verifying} onClick={verifyCode}>
                  Verify
                </Button>
                <Button type="button" size="sm" variant="secondary" loading={otp.sending} onClick={sendCode}>
                  Resend code
                </Button>
              </div>
            )}
            {otp.error && <p className="mt-2 text-sm text-danger">{otp.error}</p>}
          </div>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}
        <Button type="submit" loading={loading} disabled={!canCreateAccount} className="mt-2 w-full">
          Create account
        </Button>
      </form>
      <p className="mt-6 text-sm text-slate-500">
        Already registered?{" "}
        <Link to="/login" className="font-medium text-teal">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
