import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { roleHome } from "@/lib/roleHome";

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

    if (newPassword.length < 6) {
      setError("New password must be at least 6 characters.");
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
        <TextInput
          label={forced ? "Temporary password" : "Current password"}
          type="password"
          autoComplete="current-password"
          required
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
        />
        <TextInput
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          minLength={6}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <TextInput
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          required
          minLength={6}
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
