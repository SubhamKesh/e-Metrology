// Thin, typed fetch layer. Every UI component calls into src/hooks/*, which calls
// into this file — nothing in components/pages should call fetch() directly.

const BASE_URL = `${import.meta.env.VITE_API_BASE_URL ?? ""}/api/v1`;
const TOKEN_KEY = "maapsetu_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  reason?: string;
  constructor(status: number, message: string, reason?: string) {
    super(message);
    this.status = status;
    this.reason = reason;
  }
}

// Human-readable fallback copy for the status codes this API is documented to return.
// Endpoints that return a specific server-provided message use that instead.
const STATUS_FALLBACK: Record<number, string> = {
  401: "Your session has expired. Please sign in again.",
  403: "You don't have access to do that.",
  404: "We couldn't find that.",
  409: "That's already been claimed or already exists — refresh and try again.",
  500: "Something went wrong on our end. Please try again shortly.",
};

// FastAPI sends `detail` in two different shapes depending on the failure:
//   - a plain string, for HTTPException(status_code=..., detail="...")
//   - an array of {loc, msg, type} objects, for pydantic request-validation errors (422)
// Naively String()-ing the array shape produces "[object Object]" per element,
// since that's Object.prototype.toString()'s default — this extracts the
// actual per-field messages instead.
function extractDetailMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const loc = "loc" in item && Array.isArray((item as { loc?: unknown[] }).loc)
            ? (item as { loc: unknown[] }).loc.filter((p) => p !== "body").join(".")
            : undefined;
          const msg = String((item as { msg: unknown }).msg);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return undefined;
      })
      .filter((m): m is string => Boolean(m));
    return messages.length ? messages.join("; ") : undefined;
  }

  return undefined;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  isForm?: boolean;
  // Set true for the couple of endpoints documented as public (no auth header sent).
  public?: boolean;
  // Internal: set on the retry after a refresh, so a failed retry doesn't
  // trigger a second refresh attempt and loop.
  _isRetry?: boolean;
}

// The backend now issues short-lived (15 min) access tokens plus a
// long-lived refresh token in an httpOnly cookie (see backend
// docs/security-hardening-status.md). A single access token would have
// previously stayed valid for 7 days; to avoid every user getting silently
// logged out every 15 minutes, a 401 triggers one transparent refresh
// attempt before falling back to the old "clear token, bounce to /login"
// behavior. `credentials: "include"` is required on every request (not
// just /refresh) for the browser to send/receive that cookie at all.
let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then(async (res) => {
        if (!res.ok) return false;
        const data = (await res.json()) as { token?: string };
        if (!data.token) return false;
        setToken(data.token);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, isForm = false, public: isPublic = false, _isRetry = false } = opts;

  const headers: Record<string, string> = {};
  if (!isForm) headers["Content-Type"] = "application/json";
  if (!isPublic) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      credentials: "include", // send/receive the httpOnly refresh cookie
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }

  if (res.status === 204) return undefined as T;

  // A 401 on an authenticated request might just mean the 15-min access
  // token expired, not that the session is actually over — try one silent
  // refresh-and-retry before giving up. Skipped for /auth/* calls
  // themselves (login/register/refresh/me on initial load) so a genuinely
  // wrong password or a dead refresh cookie doesn't retry pointlessly.
  if (res.status === 401 && !isPublic && !_isRetry && !path.startsWith("/auth/")) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return request<T>(path, { ...opts, _isRetry: true });
    }
  }

  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      // non-JSON body; leave data null
    }
  }

  if (res.status === 401 && !isPublic) {
    // Session expired or token invalid — clear it so ProtectedRoute redirects
    // to /login on next render instead of retrying with a dead token.
    clearToken();
  }

  if (!res.ok) {
    const serverMessage =
      data && typeof data === "object" && "detail" in (data as Record<string, unknown>)
        ? extractDetailMessage((data as Record<string, unknown>).detail)
        : undefined;
    throw new ApiError(
      res.status,
      serverMessage ?? STATUS_FALLBACK[res.status] ?? `Request failed (${res.status}).`,
    );
  }

  return data as T;
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "GET" }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "POST", body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "PATCH", body }),
  del: <T>(path: string, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "DELETE" }),
};
