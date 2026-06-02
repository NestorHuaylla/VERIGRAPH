import type { UserRole } from "@/lib/verigraph-types";
import { getSession } from "next-auth/react";

const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
const defaultApiPort = process.env.NEXT_PUBLIC_API_PORT?.trim() || "8000";
const authStorageKey = "verigraph.auth";

export type AuthSession = {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    role: UserRole;
    is_active: boolean;
  };
};

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function isLoopbackHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function isConfiguredForLoopback(url: string | undefined): boolean {
  if (!url) {
    return true;
  }

  try {
    return isLoopbackHost(new URL(url).hostname);
  } catch {
    return false;
  }
}

export function getApiBaseUrl(): string {
  if (isBrowser() && isConfiguredForLoopback(configuredApiBaseUrl) && !isLoopbackHost(window.location.hostname)) {
    return `${window.location.protocol}//${window.location.hostname}:${defaultApiPort}`;
  }

  return configuredApiBaseUrl || `http://localhost:${defaultApiPort}`;
}

export const apiBaseUrl = getApiBaseUrl();

export function getAuthSession(): AuthSession | null {
  if (!isBrowser()) {
    return null;
  }

  const rawSession = window.localStorage.getItem(authStorageKey);
  if (!rawSession) {
    return null;
  }

  try {
    return JSON.parse(rawSession) as AuthSession;
  } catch {
    window.localStorage.removeItem(authStorageKey);
    return null;
  }
}

export function setAuthSession(session: AuthSession): void {
  window.localStorage.setItem(authStorageKey, JSON.stringify(session));
}

export function clearAuthSession(): void {
  if (isBrowser()) {
    window.localStorage.removeItem(authStorageKey);
  }
}

export function getAuthUser(): AuthSession["user"] | null {
  return getAuthSession()?.user ?? null;
}

export async function getEffectiveAuthSession(): Promise<AuthSession | null> {
  const localSession = getAuthSession();
  if (localSession?.access_token) {
    return localSession;
  }

  const nextAuthSession = await getSession();
  if (!nextAuthSession?.accessToken) {
    return null;
  }

  return {
    access_token: nextAuthSession.accessToken,
    token_type: "bearer",
    user: nextAuthSession.user
  };
}

async function parseErrorResponse(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown; message?: unknown };
    const detail = body.detail ?? body.message;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (typeof item === "object" && item !== null && "msg" in item ? String(item.msg) : String(item)))
        .join(" ");
    }
    if (detail) {
      return String(detail);
    }
  } catch {
    // Keep the status text fallback.
  }

  return response.statusText || `API error ${response.status}`;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  const session = await getEffectiveAuthSession();
  if (session?.access_token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  return fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    cache: init.cache ?? "no-store"
  });
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorResponse(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function apiGet<T>(path: string): Promise<T> {
  return apiJson<T>(path);
}

export async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  return apiJson<T>(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function apiPatch<T>(path: string, payload: unknown): Promise<T> {
  return apiJson<T>(path, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}
