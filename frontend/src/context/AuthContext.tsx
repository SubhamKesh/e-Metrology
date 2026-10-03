import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { AuthApi, type MfaSetup, type RegisterPayload } from "@/lib/endpoints";
import { ApiError, clearToken, getSessionMode, getToken, refreshSession, setSessionMode, setToken } from "@/lib/api";
import type { User } from "@/lib/types";

// What a password login can lead to: a finished session, or (officer/admin
// accounts) a second step that must be completed on the two-step page first.
export type LoginResult =
  | { kind: "session"; user: User }
  | { kind: "mfa"; mfaToken: string; setup: boolean };

// A session that exists on the server but hasn't been adopted by this screen
// yet — used so the recovery-codes screen can stay up before we "log in".
export interface PendingSession {
  user: User;
  token: string;
  recoveryCodes: string[];
}

interface AuthState {
  user: User | null;
  status: "loading" | "authed" | "guest";
  login: (email: string, password: string, rememberMe?: boolean) => Promise<LoginResult>;
  verifyMfa: (mfaToken: string, code: string) => Promise<{ user: User; recoveryCodesRemaining: number | null }>;
  beginMfaSetup: (mfaToken: string) => Promise<MfaSetup>;
  confirmMfaSetup: (mfaToken: string, code: string) => Promise<PendingSession>;
  commitSession: (session: PendingSession) => User;
  register: (payload: RegisterPayload) => Promise<User>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");

  useEffect(() => {
    let cancelled = false;

    // Restores the signed-in user on page load / browser restart:
    //   1. a stored access token that /auth/me still accepts, else
    //   2. the httpOnly refresh cookie (this is what "Remember me" relies on —
    //      access tokens only live 15 minutes).
    // Resolves to null (guest) if neither works.
    async function restoreSession(): Promise<User | null> {
      // Read before anything else: a 401 from /auth/me clears the stored mode.
      const mode = getSessionMode();

      if (getToken()) {
        try {
          return await AuthApi.me();
        } catch (err) {
          // Anything other than "token expired/invalid" (offline, 5xx) is not
          // a reason to try refreshing; treat as signed out like before.
          if (!(err instanceof ApiError) || err.status !== 401) return null;
        }
      }

      // Nothing to restore from if the user never signed in on this browser.
      if (!mode) return null;
      if (!(await refreshSession(mode))) return null;
      try {
        return await AuthApi.me();
      } catch {
        return null;
      }
    }

    restoreSession().then((restored) => {
      if (cancelled) return;
      if (restored) {
        setUser(restored);
        setStatus("authed");
      } else {
        clearToken();
        setStatus("guest");
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  // Adopts a finished session on this screen. Mode first: setToken() uses it
  // to pick localStorage vs sessionStorage.
  function startSession(nextUser: User, token: string, persistent: boolean) {
    setSessionMode(persistent ? "persistent" : "session");
    setToken(token);
    setUser(nextUser);
    setStatus("authed");
  }

  async function login(email: string, password: string, rememberMe = false): Promise<LoginResult> {
    const res = await AuthApi.login({ email, password, remember_me: rememberMe });

    // Officer/admin accounts: password accepted, second step still owed. No
    // token exists yet — hand the short-lived mfa_token to the two-step page.
    if (res.mfa_token && (res.mfa_required || res.mfa_setup_required)) {
      return { kind: "mfa", mfaToken: res.mfa_token, setup: res.mfa_setup_required };
    }
    if (!res.token || !res.user) {
      throw new ApiError(500, "Unexpected response from the server. Please try again.");
    }
    // Trust the server's answer, not the checkbox: it ignores "remember me"
    // for officer and admin accounts.
    startSession(res.user, res.token, rememberMe && res.remember_me === true);
    return { kind: "session", user: res.user };
  }

  async function verifyMfa(mfaToken: string, code: string) {
    const res = await AuthApi.mfaVerify({ mfa_token: mfaToken, code });
    if (!res.token || !res.user) {
      throw new ApiError(500, "Unexpected response from the server. Please try again.");
    }
    startSession(res.user, res.token, false);
    return { user: res.user, recoveryCodesRemaining: res.recovery_codes_remaining };
  }

  const beginMfaSetup = (mfaToken: string) => AuthApi.mfaSetup(mfaToken);

  async function confirmMfaSetup(mfaToken: string, code: string): Promise<PendingSession> {
    const res = await AuthApi.mfaConfirmSetup({ mfa_token: mfaToken, code });
    if (!res.token || !res.user || !res.recovery_codes) {
      throw new ApiError(500, "Unexpected response from the server. Please try again.");
    }
    return { user: res.user, token: res.token, recoveryCodes: res.recovery_codes };
  }

  function commitSession(session: PendingSession): User {
    startSession(session.user, session.token, false);
    return session.user;
  }

  async function register(payload: RegisterPayload) {
    const res = await AuthApi.register(payload);
    // If the backend returned a token, the account is active and we
    // treat the user as authenticated. If the token is empty (officer
    // accounts created in "pending" status), don't persist a token
    // and keep the app in the guest state — the UI will navigate to
    // a pending-approval page after register.
    if (res.token) {
      setSessionMode("session");
      setToken(res.token);
      setUser(res.user);
      setStatus("authed");
    } else {
      // pending registration: keep the user information locally so
      // the UI can show the pending page, but do not treat them as
      // authenticated for protected routes.
      setUser(res.user);
      setStatus("guest");
    }
    return res.user;
  }

  async function changePassword(currentPassword: string, newPassword: string) {
    const { token, remember_me, ...updated } = await AuthApi.changePassword({
      current_password: currentPassword,
      new_password: newPassword,
    });
    // Changing the password signed this account out everywhere — including
    // the token this screen was holding. The response carries a fresh one
    // for this device (and sets a fresh refresh cookie), so store it, or the
    // next request would 401 and bounce the user to the login page.
    setSessionMode(remember_me ? "persistent" : "session");
    setToken(token);
    setUser(updated);
    return updated;
  }

  function logout() {
    // Best-effort: revoke the refresh-token cookie server-side. Fire and
    // forget — local logout must not hang or fail just because the
    // network call did, since the whole point of logging out is to get
    // the user back to /login immediately.
    AuthApi.logout().catch(() => {});
    clearToken();
    setUser(null);
    setStatus("guest");
  }

  return (
    <AuthContext.Provider value={{
        user,
        status,
        login,
        verifyMfa,
        beginMfaSetup,
        confirmMfaSetup,
        commitSession,
        register,
        changePassword,
        logout,
      }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
