import type { UserRole } from "@/lib/verigraph-types";
import { getSession } from "next-auth/react";

const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
const defaultApiPort = process.env.NEXT_PUBLIC_API_PORT?.trim() || "8000";

// NOTA DE SEGURIDAD: el login local (/api/v1/auth/login) sigue devolviendo
// `access_token` en el body de la respuesta para que clientes de API no
// interactivos (scripts, Postman, apps moviles) puedan seguir usandolo.
// El frontend web, sin embargo, NUNCA debe leer ni persistir ese valor:
// el backend ya deja el token en una cookie httpOnly (inaccesible desde
// JavaScript), y esta app se apoya en esa cookie via `credentials: "include"`.
// Guardar el token en localStorage/variables de JS es lo que queremos evitar,
// porque cualquier XSS en la pagina podria robarlo.

export type AuthSession = {
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

// Sesion local: ya NO se guarda el JWT, solo el perfil de usuario (para
// pintar la UI sin tener que llamar a /auth/me en cada render). La cookie
// httpOnly del backend es la unica que realmente autentica las peticiones.
const userStorageKey = "verigraph.user";

export function getAuthUser(): AuthSession["user"] | null {
  if (!isBrowser()) {
    return null;
  }

  const raw = window.localStorage.getItem(userStorageKey);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as AuthSession["user"];
  } catch {
    window.localStorage.removeItem(userStorageKey);
    return null;
  }
}

export function setAuthSession(session: AuthSession): void {
  if (isBrowser()) {
    window.localStorage.setItem(userStorageKey, JSON.stringify(session.user));
  }
}

export async function clearAuthSession(): Promise<void> {
  if (isBrowser()) {
    window.localStorage.removeItem(userStorageKey);
  }
  // Le pide al backend que borre la cookie httpOnly de sesion.
  await fetch(`${getApiBaseUrl()}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include"
  }).catch(() => undefined);
}

// Descarga un archivo binario (CSV/PDF) devuelto por el API, respetando la
// misma autenticacion (cookie httpOnly o Bearer de NextAuth) que apiFetch,
// y dispara la descarga en el navegador sin necesidad de un <a href> directo
// (un link directo al API no llevaria el header Authorization del flujo
// Keycloak/NextAuth).
export async function downloadApiFile(path: string, fallbackFilename: string): Promise<void> {
  const response = await apiFetch(path, { method: "GET" });

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorResponse(response));
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filenameMatch = /filename="?([^"]+)"?/.exec(disposition);
  const filename = filenameMatch?.[1] ?? fallbackFilename;

  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
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

  // La cookie httpOnly de sesion local viaja sola gracias a credentials:"include".
  // Para el flujo Keycloak/NextAuth (que no usa la cookie del backend), seguimos
  // adjuntando el accessToken de la sesion de NextAuth via header Authorization.
  if (!headers.has("Authorization")) {
    const nextAuthSession = await getSession();
    if (nextAuthSession?.accessToken) {
      headers.set("Authorization", `Bearer ${nextAuthSession.accessToken}`);
    }
  }

  return fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    credentials: "include",
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

// Reemplaza al viejo getEffectiveAuthSession(): en vez de leer el token
// desde JS, le pregunta directamente al backend "quien soy" (la cookie
// httpOnly, o el header de NextAuth, viajan solos). Devuelve null si no
// hay sesion valida, sin exponer ningun token.
export async function fetchCurrentUser(): Promise<AuthSession["user"] | null> {
  try {
    return await apiGet<AuthSession["user"]>("/api/v1/auth/me");
  } catch {
    return null;
  }
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
