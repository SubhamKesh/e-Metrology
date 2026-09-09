import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { AuthApi, type RegisterPayload } from "@/lib/endpoints";
import { clearToken, getToken, setToken } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthState {
  user: User | null;
  status: "loading" | "authed" | "guest";
  login: (email: string, password: string) => Promise<User>;
  register: (payload: RegisterPayload) => Promise<User>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setStatus("guest");
      return;
    }
    AuthApi.me()
      .then((res) => {
        setUser(res.user);
        setStatus("authed");
      })
      .catch(() => {
        clearToken();
        setStatus("guest");
      });
  }, []);

  async function login(email: string, password: string) {
    const res = await AuthApi.login({ email, password });
    setToken(res.token);
    setUser(res.user);
    setStatus("authed");
    return res.user;
  }

  async function register(payload: RegisterPayload) {
    const res = await AuthApi.register(payload);
    // If the backend returned a token, the account is active and we
    // treat the user as authenticated. If the token is empty (officer
    // accounts created in "pending" status), don't persist a token
    // and keep the app in the guest state — the UI will navigate to
    // a pending-approval page after register.
    if (res.token) {
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
    const updated = await AuthApi.changePassword({
      current_password: currentPassword,
      new_password: newPassword,
    });
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
    <AuthContext.Provider value={{ user, status, login, register, changePassword, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
