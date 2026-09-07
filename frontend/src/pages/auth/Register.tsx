import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { TextInput, SelectInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { roleHome } from "@/lib/roleHome";
import type { Role } from "@/lib/types";

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "owner", label: "Business / User — I own instruments" },
  { value: "lmo", label: "Legal Metrology Officer" },
  { value: "gatc", label: "GATC" },
];

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    role: "owner" as Role,
    org_name: "",
    contact: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const needsOrgType = form.role === "lmo" || form.role === "gatc";

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await register({
        name: form.name,
        email: form.email,
        password: form.password,
        role: form.role,
        org_type: needsOrgType ? (form.role === "lmo" ? "LMO" : "GATC") : null,
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
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <SelectInput
          label="I am"
          required
          value={form.role}
          onChange={(e) => set("role", e.target.value as Role)}
          options={ROLE_OPTIONS}
        />
        <TextInput label="Full name" required value={form.name} onChange={(e) => set("name", e.target.value)} />
        <TextInput
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={form.email}
          onChange={(e) => set("email", e.target.value)}
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
          label={form.role === "owner" ? "Business name" : "Organisation name"}
          value={form.org_name}
          onChange={(e) => set("org_name", e.target.value)}
        />
        <TextInput
          label="Contact number"
          type="tel"
          value={form.contact}
          onChange={(e) => set("contact", e.target.value)}
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
