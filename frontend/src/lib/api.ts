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

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  isForm?: boolean;
  // Set true for the couple of endpoints documented as public (no auth header sent).
  public?: boolean;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, isForm = false, public: isPublic = false } = opts;

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
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }

  if (res.status === 204) return undefined as T;

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
        ? String((data as Record<string, unknown>).detail)
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
