import { type ChangeEvent, type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { roleHome } from "@/lib/roleHome";
import { isValidPassword, PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, PASSWORD_POLICY_ERROR } from "@/lib/validation";
import { PasswordRequirements } from "@/components/ui/PasswordRequirements";

interface PasswordInputProps {
  label: string;
  autoComplete: "current-password" | "new-password";
  value: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
  minLength?: number;
  maxLength?: number;
}

function PasswordInput({ label, autoComplete, value, onChange, minLength, maxLength }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative">
      <TextInput
        label={label}
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        required
        minLength={minLength}
        maxLength={maxLength}
        value={value}
        onChange={onChange}
        className="pr-12"
      />
      <button
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
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
          {visible ? (
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
  );
}

export default function ChangePassword() {
  const { user, changePassword } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const forced = user?.must_change_password ?? false;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!isValidPassword(newPassword)) {
      setError(PASSWORD_POLICY_ERROR);
      return;
    }
    if (newPassword === currentPassword) {
      setError("New password must be different from your current password.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New passwords don't match.");
      return;
    }

    setLoading(true);
    try {
      const updated = await changePassword(currentPassword, newPassword);
      navigate(roleHome(updated.role), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      title={forced ? "Set your password" : "Change password"}
      subtitle={
        forced
          ? "Your account was created by an administrator with a temporary password. Set a new one to continue."
          : "Update the password on your account."
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <PasswordInput
          label={forced ? "Temporary password" : "Current password"}
          autoComplete="current-password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
        />
        <PasswordInput
          label="New password"
          autoComplete="new-password"
          minLength={PASSWORD_MIN_LENGTH}
          maxLength={PASSWORD_MAX_LENGTH}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <PasswordRequirements password={newPassword} />
        <PasswordInput
          label="Confirm new password"
          autoComplete="new-password"
          minLength={PASSWORD_MIN_LENGTH}
          maxLength={PASSWORD_MAX_LENGTH}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <Button type="submit" loading={loading} className="mt-2 w-full">
          Save new password
        </Button>
      </form>
    </AuthLayout>
  );
}
