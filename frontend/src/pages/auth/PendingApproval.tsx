import { Link } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/Button";

export default function PendingApproval() {
  const { user, logout } = useAuth();

  return (
    <AuthLayout title="Account pending approval" subtitle="Your account is awaiting admin approval.">
      <div className="prose max-w-none">
        <p>
          Thanks for registering{user ? `, ${user.name}` : ""}. An administrator must approve officer accounts before
          they can sign in. You will receive an email when your account is approved.
        </p>
        <p className="text-sm text-slate-500">If you need help, contact the department using your registered email.</p>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button onClick={() => logout()} className="w-full sm:w-36">
            Sign out
          </Button>
          <Link to="/login" className="inline-flex h-11 items-center justify-center rounded-md px-4 text-sm font-medium text-teal hover:bg-teal-50">
            Return to sign in
          </Link>
        </div>
      </div>
    </AuthLayout>
  );
}
