import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { useAuth, type PendingSession } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import type { MfaSetup } from "@/lib/endpoints";
import { roleHome } from "@/lib/roleHome";

interface TwoFactorState {
  mfaToken?: string;
  setup?: boolean;
  email?: string;
  from?: { pathname: string };
}

// Spaces every 4 characters so the manual-entry key is readable.
const groupKey = (secret: string) => secret.replace(/(.{4})/g, "$1 ").trim();

export default function TwoFactor() {
  const location = useLocation() as { state?: TwoFactorState };
  const state = location.state;

  // The mfa_token only ever travels in router state (never storage). Landing
  // here without one — a bookmark, a refresh after it expired — means "sign in again".
  if (!state?.mfaToken) return <Navigate to="/login" replace />;

  return state.setup ? (
    <Setup mfaToken={state.mfaToken} from={state.from} />
  ) : (
    <Verify mfaToken={state.mfaToken} email={state.email} from={state.from} />
  );
}

function BackToSignIn() {
  return (
    <p className="mt-6 text-sm text-slate-500">
      <Link to="/login" replace className="font-medium text-teal underline underline-offset-2">
        Back to sign in
      </Link>
    </p>
  );
}

function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md bg-danger-50 px-3 py-2 text-sm text-danger">
      {message}
    </p>
  );
}

// ---------------------------------------------------------------- verify

function Verify({ mfaToken, email, from }: { mfaToken: string; email?: string; from?: { pathname: string } }) {
  const { verifyMfa } = useAuth();
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [recoveryLeft, setRecoveryLeft] = useState<{ remaining: number; dest: string } | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const value = code.trim();
    if (!useRecovery && !/^\d{6}$/.test(value)) {
      setError("Enter the 6-digit code from your authenticator app.");
      return;
    }
    if (useRecovery && value.length < 6) {
      setError("Enter one of your recovery codes.");
      return;
    }
    setLoading(true);
    try {
      const { user, recoveryCodesRemaining } = await verifyMfa(mfaToken, value);
      const dest = from?.pathname ?? roleHome(user.role);
      if (recoveryCodesRemaining !== null) {
        // Signed in with a one-time recovery code: tell them how many are left.
        setRecoveryLeft({ remaining: recoveryCodesRemaining, dest });
      } else {
        navigate(dest, { replace: true });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  if (recoveryLeft) {
    return (
      <AuthLayout seo="/two-step" title="You're signed in" subtitle="You used a recovery code.">
        <p className="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-700">
          {recoveryLeft.remaining > 0
            ? `You have ${recoveryLeft.remaining} recovery code${recoveryLeft.remaining === 1 ? "" : "s"} left. `
            : "That was your last recovery code. "}
          Each one works only once. If you've lost your phone or are running low, ask an administrator to reset your
          two-step verification so you can set up a new authenticator and get fresh codes.
        </p>
        <Button className="mt-5 w-full" onClick={() => navigate(recoveryLeft.dest, { replace: true })}>
          Continue
        </Button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout seo="/two-step"
      title="Two-step verification"
      subtitle={email ? `Signing in as ${email}.` : "Confirm it's really you."}
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <TextInput
          label={useRecovery ? "Recovery code" : "6-digit code"}
          hint={
            useRecovery
              ? "One of the codes you saved when you set up two-step verification, e.g. k7m2x-q9d4p. Each works once."
              : "Open your authenticator app and enter the current code for MaapSetu."
          }
          inputMode={useRecovery ? "text" : "numeric"}
          autoComplete="one-time-code"
          autoFocus
          maxLength={useRecovery ? 32 : 6}
          required
          value={code}
          onChange={(e) => setCode(useRecovery ? e.target.value : e.target.value.replace(/\D/g, "").slice(0, 6))}
        />
        <ErrorLine message={error} />
        <Button type="submit" loading={loading} className="mt-1 w-full">
          Verify and sign in
        </Button>
        <button
          type="button"
          onClick={() => {
            setUseRecovery((v) => !v);
            setCode("");
            setError(null);
          }}
          className="self-start text-sm font-medium text-teal underline underline-offset-2"
        >
          {useRecovery ? "Use my authenticator app instead" : "Use a recovery code instead"}
        </button>
      </form>
      <BackToSignIn />
    </AuthLayout>
  );
}

// ----------------------------------------------------------------- setup

function Setup({ mfaToken, from }: { mfaToken: string; from?: { pathname: string } }) {
  const { beginMfaSetup, confirmMfaSetup, commitSession } = useAuth();
  const navigate = useNavigate();
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<PendingSession | null>(null);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const requested = useRef(false);

  // Ask for the secret once (React StrictMode runs effects twice in dev; the
  // server also returns the same secret on a repeat call, so either way the
  // QR code on screen matches what the server expects).
  useEffect(() => {
    if (requested.current) return;
    requested.current = true;
    beginMfaSetup(mfaToken)
      .then(setSetup)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Couldn't start setup. Try again."));
  }, [beginMfaSetup, mfaToken]);

  async function onConfirm(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!/^\d{6}$/.test(code)) {
      setError("Enter the 6-digit code your authenticator app is showing.");
      return;
    }
    setLoading(true);
    try {
      // Server enables two-step verification and returns the recovery codes
      // once. We hold the new session back until they've been saved.
      setPending(await confirmMfaSetup(mfaToken, code));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  function codesText(codes: string[]) {
    return `MaapSetu recovery codes\nEach code works once. Keep them somewhere safe and private.\n\n${codes.join("\n")}\n`;
  }

  async function copyCodes(codes: string[]) {
    try {
      await navigator.clipboard.writeText(codes.join("\n"));
      setCopied(true);
    } catch {
      setCopied(false); // clipboard blocked — the codes are still on screen and downloadable
    }
  }

  function downloadCodes(codes: string[]) {
    const url = URL.createObjectURL(new Blob([codesText(codes)], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "maapsetu-recovery-codes.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---- step 3: save your recovery codes
  if (pending) {
    return (
      <AuthLayout seo="/two-step" title="Save your recovery codes" subtitle="Two-step verification is now on.">
        <p className="text-sm text-slate-600">
          If you lose your phone, each of these codes lets you sign in once. They're shown{" "}
          <strong>only now</strong> — save them somewhere safe and private.
        </p>
        <ul
          aria-label="Recovery codes"
          className="mt-4 grid grid-cols-2 gap-2 rounded-md border border-line bg-white p-4 font-mono text-sm text-ink"
        >
          {pending.recoveryCodes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={() => copyCodes(pending.recoveryCodes)}>
            {copied ? "Copied" : "Copy codes"}
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={() => downloadCodes(pending.recoveryCodes)}>
            Download as text file
          </Button>
        </div>
        <label className="mt-5 flex cursor-pointer select-none items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={saved}
            onChange={(e) => setSaved(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-line accent-teal"
          />
          I've saved these recovery codes somewhere safe.
        </label>
        <Button
          className="mt-4 w-full"
          disabled={!saved}
          onClick={() => {
            const user = commitSession(pending);
            navigate(from?.pathname ?? roleHome(user.role), { replace: true });
          }}
        >
          Continue
        </Button>
      </AuthLayout>
    );
  }

  // ---- steps 1 + 2: scan the QR code, enter a code
  return (
    <AuthLayout seo="/two-step"
      title="Set up two-step verification"
      subtitle="Officer and administrator accounts need a code from an authenticator app every time they sign in."
    >
      {loadError ? (
        <div className="flex flex-col gap-4">
          <ErrorLine message={loadError} />
          <BackToSignIn />
        </div>
      ) : !setup ? (
        <p className="text-sm text-slate-500">Preparing your setup code…</p>
      ) : (
        <form onSubmit={onConfirm} className="flex flex-col gap-4">
          <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600">
            <li>
              Install an authenticator app on your phone (Google Authenticator, Microsoft Authenticator, Authy…).
            </li>
            <li>Scan this QR code, or enter the key below by hand.</li>
            <li>Type the 6-digit code the app shows, then press Turn on.</li>
          </ol>
          <img
            src={setup.qr_data_uri}
            alt="QR code that adds your MaapSetu account to an authenticator app"
            width={192}
            height={192}
            className="self-center rounded-md border border-line bg-white p-2"
          />
          <div className="text-center text-xs text-slate-500">
            Can't scan? Enter this key:
            <div className="mt-1 select-all break-all font-mono text-sm text-ink">{groupKey(setup.secret)}</div>
          </div>
          <TextInput
            label="6-digit code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          />
          <ErrorLine message={error} />
          <Button type="submit" loading={loading} className="w-full">
            Turn on two-step verification
          </Button>
        </form>
      )}
      {!loadError && <BackToSignIn />}
    </AuthLayout>
  );
}
