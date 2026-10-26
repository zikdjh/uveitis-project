const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let refreshPromise: Promise<boolean> | null = null;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function apiUrl(path: string): string {
  return `${baseUrl}${path}`;
}

export function getCsrfToken(): string {
  const prefix = "uveitis_csrf=";
  const value = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix));
  return value ? decodeURIComponent(value.slice(prefix.length)) : "";
}

export function csrfHeaders(method = "POST"): HeadersInit {
  if (!unsafeMethods.has(method.toUpperCase())) return {};
  const token = getCsrfToken();
  return token ? { "X-CSRF-Token": token } : {};
}

function requestHeaders(init?: RequestInit): Headers {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  for (const [key, value] of Object.entries(csrfHeaders(method))) {
    headers.set(key, value);
  }
  return headers;
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), {
    ...init,
    headers: requestHeaders(init),
    credentials: "include",
  });
}

function canAttemptRefresh(path: string): boolean {
  return !path.endsWith("/auth/login")
    && !path.endsWith("/auth/admin/login")
    && !path.includes("/auth/refresh");
}

async function performRefresh(): Promise<boolean> {
  const response = await fetch(apiUrl("/api/v1/auth/refresh"), {
    method: "POST",
    headers: requestHeaders({ method: "POST" }),
    credentials: "include",
  });
  return response.ok;
}

function refreshOnce(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

export async function authorizedFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  let response = await send(path, init);
  if (response.status === 401 && canAttemptRefresh(path)) {
    if (await refreshOnce()) {
      response = await send(path, init);
    }
  }
  if (
    response.status === 401
    && !path.endsWith("/auth/login")
    && !path.endsWith("/auth/admin/login")
  ) {
    window.dispatchEvent(new Event("auth:unauthorized"));
  }
  return response;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authorizedFetch(path, init);
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  try {
    const data = JSON.parse(text) as { detail?: string | Array<{ msg?: string }> };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg).join("；");
  } catch {
    // Fall back to the raw response body.
  }
  return text || `请求失败（${response.status}）`;
}
