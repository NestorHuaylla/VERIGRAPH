"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Loader2, LogIn, ShieldAlert } from "lucide-react";

import { ApiError, apiGet, getEffectiveAuthSession, type AuthSession } from "@/lib/api";
import type { UserRole } from "@/lib/verigraph-types";
import { StatusPill } from "@/components/status-pill";

type GuardUser = AuthSession["user"];
type GuardState = "checking" | "allowed" | "anonymous" | "forbidden" | "inactive" | "api_error";

const roleLabels: Record<UserRole, string> = {
  reporter: "reporter",
  analyst: "analyst",
  admin: "admin",
  legal: "legal"
};

export function InternalRouteGuard({
  allowedRoles,
  children,
  title = "Acceso interno"
}: {
  allowedRoles: readonly UserRole[];
  children: ReactNode;
  title?: string;
}) {
  const [state, setState] = useState<GuardState>("checking");
  const [user, setUser] = useState<GuardUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setError(null);

    setState("checking");

    void getEffectiveAuthSession()
      .then((session) => {
        if (!alive) {
          return;
        }
        const sessionUser = session?.user ?? null;
        setUser(sessionUser);

        if (!session?.access_token || !sessionUser) {
          setState("anonymous");
          return null;
        }

        return apiGet<GuardUser>("/api/v1/auth/me");
      })
      .then((validatedUser) => {
        if (!alive || !validatedUser) {
          return;
        }
        setUser(validatedUser);

        if (!validatedUser.is_active) {
          setState("inactive");
          return;
        }

        setState(isAllowedRole(validatedUser.role, allowedRoles) ? "allowed" : "forbidden");
      })
      .catch((caughtError) => {
        if (!alive) {
          return;
        }

        if (caughtError instanceof ApiError && caughtError.status === 401) {
          setState("anonymous");
          return;
        }

        if (caughtError instanceof ApiError && caughtError.status === 403) {
          setState("inactive");
          return;
        }

        setError(caughtError instanceof ApiError ? caughtError.detail : "No se pudo validar la sesion con el API.");
        setState("api_error");
      });

    return () => {
      alive = false;
    };
  }, [allowedRoles]);

  if (state === "checking") {
    return (
      <section className="grid min-h-[320px] place-items-center rounded-md border border-border bg-panel p-6 text-slate-300">
        <div className="flex items-center gap-3 text-sm">
          <Loader2 className="animate-spin" size={18} />
          Validando acceso
        </div>
      </section>
    );
  }

  if (state !== "allowed") {
    return <AccessBlocked title={title} state={state} user={user} allowedRoles={allowedRoles} error={error} />;
  }

  return <>{children}</>;
}

function AccessBlocked({
  title,
  state,
  user,
  allowedRoles,
  error
}: {
  title: string;
  state: Exclude<GuardState, "checking" | "allowed">;
  user: GuardUser | null;
  allowedRoles: readonly UserRole[];
  error: string | null;
}) {
  const message =
    state === "anonymous"
      ? "Inicia sesion con una cuenta interna para continuar."
      : state === "inactive"
        ? "La cuenta esta inactiva. Un admin debe reactivarla."
        : state === "api_error"
          ? "No se pudo validar la sesion interna."
          : "Tu rol actual no tiene permisos para esta vista.";

  return (
    <section className="mx-auto grid max-w-xl gap-5 rounded-md border border-border bg-panel p-6">
      <div className="flex items-start gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-warning bg-[#2c1d05] text-amber-200">
          <ShieldAlert size={18} />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-white">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">{message}</p>
          {error ? <p className="mt-2 text-sm text-amber-100">{error}</p> : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {user ? <StatusPill label={user.email} tone="neutral" /> : null}
        {user ? <StatusPill label={user.role} tone={state === "forbidden" ? "high" : "neutral"} /> : null}
        <StatusPill label={`roles: ${allowedRoles.map((role) => roleLabels[role]).join(", ")}`} tone="neutral" />
      </div>

      <Link
        href="/login"
        className="focus-ring inline-flex h-11 w-fit items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white transition hover:bg-blue-500"
      >
        <LogIn size={17} />
        Ir a login
      </Link>
    </section>
  );
}

function isAllowedRole(role: string | undefined, allowedRoles: readonly UserRole[]): boolean {
  return Boolean(role && allowedRoles.includes(role as UserRole));
}
