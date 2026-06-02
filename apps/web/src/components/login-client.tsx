"use client";

import { FormEvent, useEffect, useState } from "react";
import { AlertTriangle, Building2, Loader2, LockKeyhole, LogOut, UserPlus } from "lucide-react";
import { signIn, signOut } from "next-auth/react";

import { ApiError, apiPost, clearAuthSession, getEffectiveAuthSession, setAuthSession } from "@/lib/api";
import type { AuthResponse } from "@/lib/verigraph-types";
import { StatusPill } from "@/components/status-pill";

type Mode = "login" | "register";

export function LoginClient() {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [user, setUser] = useState<AuthResponse["user"] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const keycloakEnabled = Boolean(process.env.NEXT_PUBLIC_KEYCLOAK_ENABLED === "true");

  useEffect(() => {
    void getEffectiveAuthSession().then((session) => setUser(session?.user ?? null));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const session = await apiPost<AuthResponse>(mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register", {
        email: email.trim(),
        password
      });
      setAuthSession(session);
      setUser(session.user);
      setPassword("");
    } catch (caughtError) {
      const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo conectar con el API.";
      setError(detail);
    } finally {
      setLoading(false);
    }
  }

  function handleLogout() {
    clearAuthSession();
    void signOut({ redirect: false });
    setUser(null);
  }

  async function handleKeycloakLogin() {
    setError(null);
    await signIn("keycloak", { callbackUrl: "/dashboard" });
  }

  return (
    <section className="mx-auto max-w-md rounded-md border border-border bg-panel p-6">
      <div className="mb-6 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-md border border-accent bg-[#0c1c35] text-blue-200">
          <LockKeyhole size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-white">Acceso interno</h1>
          <p className="text-sm text-slate-400">Analistas, admin y equipo legal.</p>
        </div>
      </div>

      {user ? (
        <div className="grid gap-4">
          <div className="grid gap-3 rounded-md border border-border bg-[#0a111d] p-4 text-sm text-slate-300">
            <p className="text-white">{user.email}</p>
            <div className="flex flex-wrap gap-2">
              <StatusPill label={user.role} tone="neutral" />
              <StatusPill label={user.is_active ? "activo" : "inactivo"} tone={user.is_active ? "low" : "critical"} />
            </div>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-md border border-border bg-[#0a111d] px-5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
          >
            <LogOut size={18} />
            Cerrar sesion
          </button>
        </div>
      ) : (
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <div className="grid grid-cols-2 rounded-md border border-border bg-[#0a111d] p-1">
            <button
              type="button"
              onClick={() => setMode("login")}
              className={`focus-ring h-10 rounded px-3 text-sm ${mode === "login" ? "bg-accent text-white" : "text-slate-300"}`}
            >
              Entrar
            </button>
            <button
              type="button"
              onClick={() => setMode("register")}
              className={`focus-ring inline-flex h-10 items-center justify-center gap-2 rounded px-3 text-sm ${
                mode === "register" ? "bg-accent text-white" : "text-slate-300"
              }`}
            >
              <UserPlus size={16} />
              Reporter
            </button>
          </div>
          <label className="grid gap-2 text-sm text-slate-300">
            Email
            <input
              className="focus-ring h-12 rounded-md border border-border bg-[#0a111d] px-4 text-white"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
          </label>
          <label className="grid gap-2 text-sm text-slate-300">
            Password
            <input
              className="focus-ring h-12 rounded-md border border-border bg-[#0a111d] px-4 text-white"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={8}
              required
            />
          </label>
          {error ? (
            <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              <AlertTriangle className="mt-0.5 shrink-0" size={18} />
              <p>{error}</p>
            </div>
          ) : null}
          <button
            type="submit"
            disabled={loading}
            className="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-md bg-accent px-5 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:cursor-wait disabled:opacity-70"
          >
            {loading ? <Loader2 className="animate-spin" size={18} /> : null}
            {mode === "login" ? "Entrar" : "Crear cuenta"}
          </button>
          {keycloakEnabled ? (
            <button
              type="button"
              onClick={handleKeycloakLogin}
              className="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-md border border-border bg-[#0a111d] px-5 text-sm font-semibold text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
            >
              <Building2 size={18} />
              Entrar con Keycloak
            </button>
          ) : null}
        </form>
      )}
    </section>
  );
}
