import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { roleHome } from "@/lib/roleHome";
import type { Role } from "@/lib/types";
import { isValidName, isValidEmail, isValidPhone } from "@/lib/validation";

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
  }

  function handleContactChange(value: string) {
    const digitsOnly = value.replace(/\D/g, "").slice(0, 10);
    set("contact", digitsOnly);
    setFieldErrors((f) => ({
      ...f,
      contact: digitsOnly.length > 0 && digitsOnly.length < 10 ? "Enter a valid 10-digit mobile number." : undefined,
    }));
  }

  function validateAllOnSubmit(): boolean {
    const nameError = !isValidName(form.name) ? "Only letters and spaces are allowed." : undefined;
    const emailError = !isValidEmail(form.email) ? "Enter a valid email address." : undefined;
    const contactError =
      form.contact.length > 0 && !isValidPhone(form.contact)
        ? "Enter a valid 10-digit mobile number."
        : undefined;

    const errors: FieldErrors = { name: nameError, email: emailError, contact: contactError };
    setFieldErrors(errors);

    return !nameError && !emailError && !contactError;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!validateAllOnSubmit()) {
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
          minLength={8}
          value={form.password}
          onChange={(e) => set("password", e.target.value)}
        />
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
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button type="submit" loading={loading} className="mt-2 w-full">
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
