"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, ShieldCheck, UserCog, UserX } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ApiError, apiGet, apiPatch } from "@/lib/api";
import type { UserListItem, UserRole, UserUpdateResponse } from "@/lib/verigraph-types";
import { StatusPill } from "@/components/status-pill";

const roleLabels: Record<UserRole, string> = {
  reporter: "Reporter",
  analyst: "Analyst",
  admin: "Admin",
  legal: "Legal"
};

const userRoles: UserRole[] = ["reporter", "analyst", "admin", "legal"];

const demoUsers: UserListItem[] = [
  {
    id: "demo-user-admin",
    email: "admin@verigraph.local",
    role: "admin",
    is_active: true,
    created_at: "2026-05-27T08:30:00Z",
    updated_at: null
  },
  {
    id: "demo-user-analyst",
    email: "analyst@verigraph.local",
    role: "analyst",
    is_active: true,
    created_at: "2026-05-27T09:00:00Z",
    updated_at: null
  },
  {
    id: "demo-user-reporter",
    email: "reporter@verigraph.local",
    role: "reporter",
    is_active: false,
    created_at: "2026-05-27T09:30:00Z",
    updated_at: null
  }
];

type LoadState = {
  loading: boolean;
  error: string | null;
  demo: boolean;
};

export function UsersClient() {
  const [users, setUsers] = useState<UserListItem[]>(demoUsers);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, error: null, demo: true });
  const [updatingUserId, setUpdatingUserId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const activeUsers = useMemo(() => users.filter((user) => user.is_active).length, [users]);
  const internalUsers = useMemo(
    () => users.filter((user) => user.role === "admin" || user.role === "analyst" || user.role === "legal").length,
    [users]
  );

  const loadUsers = useCallback(async () => {
    setLoadState((current) => ({ ...current, loading: true }));
    setActionError(null);
    setActionMessage(null);

    try {
      const response = await apiGet<UserListItem[]>("/api/v1/users?limit=200");
      setUsers(response);
      setLoadState({ loading: false, error: null, demo: false });
    } catch (caughtError) {
      const detail =
        caughtError instanceof ApiError && caughtError.status === 403
          ? "Solo un usuario admin puede gestionar roles y cuentas."
          : caughtError instanceof ApiError && caughtError.status === 401
            ? "Inicia sesion con usuario admin para cargar usuarios reales."
            : caughtError instanceof ApiError
              ? caughtError.detail
              : "No se pudo conectar con el API.";
      setUsers(demoUsers);
      setLoadState({ loading: false, error: detail, demo: true });
    }
  }, []);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  async function updateUserRole(user: UserListItem, role: UserRole) {
    if (user.role === role) {
      return;
    }

    if (loadState.demo) {
      applyUserUpdate({
        id: user.id,
        email: user.email,
        role,
        is_active: user.is_active,
        message: `Rol demo actualizado a ${roleLabels[role]}.`
      });
      return;
    }

    setUpdatingUserId(user.id);
    setActionError(null);
    setActionMessage(null);
    try {
      const response = await apiPatch<UserUpdateResponse>(`/api/v1/users/${user.id}/role`, { role });
      applyUserUpdate(response);
    } catch (caughtError) {
      const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo actualizar el rol.";
      setActionError(detail);
    } finally {
      setUpdatingUserId(null);
    }
  }

  async function updateUserActive(user: UserListItem, isActive: boolean) {
    if (user.is_active === isActive) {
      return;
    }

    if (loadState.demo) {
      applyUserUpdate({
        id: user.id,
        email: user.email,
        role: user.role,
        is_active: isActive,
        message: isActive ? "Usuario demo activado." : "Usuario demo desactivado."
      });
      return;
    }

    setUpdatingUserId(user.id);
    setActionError(null);
    setActionMessage(null);
    try {
      const response = await apiPatch<UserUpdateResponse>(`/api/v1/users/${user.id}/active`, {
        is_active: isActive
      });
      applyUserUpdate(response);
    } catch (caughtError) {
      const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo actualizar el estado del usuario.";
      setActionError(detail);
    } finally {
      setUpdatingUserId(null);
    }
  }

  function applyUserUpdate(response: UserUpdateResponse) {
    setUsers((current) =>
      current.map((user) =>
        user.id === response.id
          ? {
              ...user,
              role: response.role,
              is_active: response.is_active,
              updated_at: new Date().toISOString()
            }
          : user
      )
    );
    setActionError(null);
    setActionMessage(response.message);
  }

  return (
    <section className="grid gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Usuarios y roles</h1>
          <p className="mt-2 text-sm text-slate-400">
            Control de acceso interno para analistas, administradores, equipo legal y reportantes.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadUsers()}
          className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-panel px-4 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
        >
          <RefreshCw className={loadState.loading ? "animate-spin" : ""} size={16} />
          Refrescar
        </button>
      </div>

      {loadState.error ? (
        <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <AlertTriangle className="mt-0.5 shrink-0" size={18} />
          <p>
            {loadState.demo ? "Vista local activa. " : ""}
            {loadState.error}
          </p>
        </div>
      ) : null}

      {actionError ? (
        <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <AlertTriangle className="mt-0.5 shrink-0" size={18} />
          <p>{actionError}</p>
        </div>
      ) : null}

      {actionMessage ? (
        <div className="flex items-start gap-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
          <CheckCircle2 className="mt-0.5 shrink-0" size={18} />
          <p>{actionMessage}</p>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard label="Usuarios" value={users.length} />
        <MetricCard label="Activos" value={activeUsers} />
        <MetricCard label="Internos" value={internalUsers} />
      </div>

      <div className="overflow-x-auto rounded-md border border-border bg-panel">
        <table className="min-w-[860px] w-full border-collapse text-left text-sm">
          <thead className="border-b border-border bg-[#0a111d] text-slate-400">
            <tr>
              <th className="px-4 py-3 font-medium">Usuario</th>
              <th className="px-4 py-3 font-medium">Rol</th>
              <th className="px-4 py-3 font-medium">Estado</th>
              <th className="px-4 py-3 font-medium">Creado</th>
              <th className="px-4 py-3 font-medium">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className="border-b border-border last:border-0">
                <td className="px-4 py-4">
                  <div className="grid gap-1">
                    <span className="break-words text-white">{user.email}</span>
                    <span className="text-xs text-slate-400">{user.id.slice(0, 12)}</span>
                  </div>
                </td>
                <td className="px-4 py-4">
                  <label className="sr-only" htmlFor={`role-${user.id}`}>
                    Rol de {user.email}
                  </label>
                  <select
                    id={`role-${user.id}`}
                    value={user.role}
                    disabled={updatingUserId === user.id}
                    onChange={(event) => void updateUserRole(user, event.target.value as UserRole)}
                    className="focus-ring h-10 rounded-md border border-border bg-[#0a111d] px-3 text-sm text-white disabled:cursor-wait disabled:opacity-60"
                  >
                    {userRoles.map((role) => (
                      <option key={role} value={role}>
                        {roleLabels[role]}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-4">
                  <StatusPill label={user.is_active ? "Activo" : "Inactivo"} tone={user.is_active ? "low" : "critical"} />
                </td>
                <td className="px-4 py-4 text-slate-300">{formatDate(user.created_at)}</td>
                <td className="px-4 py-4">
                  <div className="flex flex-wrap gap-2">
                    {user.is_active ? (
                      <ActionButton
                        label="Desactivar"
                        icon={UserX}
                        disabled={updatingUserId === user.id}
                        onClick={() => void updateUserActive(user, false)}
                      />
                    ) : (
                      <ActionButton
                        label="Activar"
                        icon={ShieldCheck}
                        disabled={updatingUserId === user.id}
                        onClick={() => void updateUserActive(user, true)}
                      />
                    )}
                    {updatingUserId === user.id ? <Loader2 className="mt-2 animate-spin text-slate-400" size={16} /> : null}
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-sm text-slate-400">
                  No hay usuarios registrados.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-panel p-5">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-3 text-3xl font-semibold text-white">{value}</p>
    </div>
  );
}

function ActionButton({
  label,
  icon: Icon,
  disabled,
  onClick
}: {
  label: string;
  icon: LucideIcon;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="focus-ring inline-flex h-9 items-center gap-2 rounded-md border border-border bg-[#0a111d] px-3 text-xs text-slate-200 transition hover:border-slate-500 hover:bg-[#172236] disabled:cursor-not-allowed disabled:opacity-40"
    >
      <Icon size={14} />
      {label}
    </button>
  );
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("es-PE");
}
