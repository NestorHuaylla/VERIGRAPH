"use client";

import type { ComponentType } from "react";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowUpRight, CheckCircle2, Filter, RefreshCw, XCircle } from "lucide-react";

import { apiFetch } from "@/lib/api";
import {
  demoDashboardData,
  filterDeliveries,
  formatMetricValue,
  type DashboardData,
  type NotificationDeliveryChannel,
  type NotificationDeliveryListItem,
  type NotificationDeliveryStatus,
  type NotificationMetricsResponse,
  type NotificationDeliveryStatusPayload
} from "@/lib/notification-dashboard";
import { StatusPill } from "@/components/status-pill";

type LoadState = {
  loading: boolean;
  error: string | null;
  demo: boolean;
};

class DashboardAuthError extends Error {
  constructor() {
    super("Los indicadores operativos completos requieren una cuenta interna.");
    this.name = "DashboardAuthError";
  }
}

const deliveryStatuses: Array<NotificationDeliveryStatus | "all"> = ["all", "pending", "sent", "failed"];
const deliveryChannels: Array<NotificationDeliveryChannel | "all"> = ["all", "webhook", "email", "slack"];

async function fetchDashboardData(): Promise<DashboardData> {
  const [metricsResponse, deliveriesResponse] = await Promise.all([
    apiFetch("/api/v1/notifications/metrics"),
    apiFetch("/api/v1/notifications/deliveries?limit=100")
  ]);

  if (!metricsResponse.ok || !deliveriesResponse.ok) {
    if (metricsResponse.status === 401 || deliveriesResponse.status === 401) {
      throw new DashboardAuthError();
    }
    throw new Error(`API error ${metricsResponse.status}/${deliveriesResponse.status}`);
  }

  return {
    metrics: (await metricsResponse.json()) as NotificationMetricsResponse,
    deliveries: (await deliveriesResponse.json()) as NotificationDeliveryListItem[]
  };
}

async function patchDeliveryStatus(
  deliveryId: string,
  payload: NotificationDeliveryStatusPayload
): Promise<void> {
  const response = await apiFetch(`/api/v1/notifications/deliveries/${deliveryId}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`API error ${response.status}`);
  }
}

export function DashboardClient() {
  const [data, setData] = useState<DashboardData>(demoDashboardData);
  const [statusFilter, setStatusFilter] = useState<NotificationDeliveryStatus | "all">("all");
  const [channelFilter, setChannelFilter] = useState<NotificationDeliveryChannel | "all">("all");
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, error: null, demo: true });

  useEffect(() => {
    let alive = true;

    void (async () => {
      try {
        const nextData = await fetchDashboardData();
        if (!alive) {
          return;
        }
        setData(nextData);
        setLoadState({ loading: false, error: null, demo: false });
      } catch (error) {
        if (!alive) {
          return;
        }
        setData(demoDashboardData);
        setLoadState({
          loading: false,
          error:
            error instanceof DashboardAuthError
              ? "Vista publica de muestra. Inicia sesion como admin/analista para ver indicadores reales."
              : error instanceof Error
                ? error.message
                : "No se pudo cargar el panel.",
          demo: true
        });
      }
    })();

    return () => {
      alive = false;
    };
  }, []);

  const filteredDeliveries = useMemo(
    () => filterDeliveries(data.deliveries, statusFilter, channelFilter),
    [channelFilter, data.deliveries, statusFilter]
  );

  const metrics = data.metrics;

  async function handleMarkStatus(delivery: NotificationDeliveryListItem, status: NotificationDeliveryStatus) {
    if (loadState.demo) {
      setData((current) => ({
        ...current,
        deliveries: current.deliveries.map((item) =>
          item.id === delivery.id
            ? {
                ...item,
                status,
                attempts: status === "failed" ? item.attempts + 1 : item.attempts,
                last_error: status === "failed" ? delivery.last_error ?? "Marcado manualmente como fallido." : null,
                sent_at: status === "sent" ? new Date().toISOString() : item.sent_at,
                next_attempt_at: status === "sent" || status === "failed" ? null : item.next_attempt_at
              }
            : item
        )
      }));
      return;
    }

    try {
      await patchDeliveryStatus(delivery.id, {
        status,
        error: status === "failed" ? delivery.last_error ?? "Marcado manualmente como fallido." : null
      });
      setData((current) => ({
        ...current,
        deliveries: current.deliveries.map((item) =>
          item.id === delivery.id
            ? {
                ...item,
                status,
                attempts: status === "failed" ? item.attempts + 1 : item.attempts,
                last_error: status === "failed" ? delivery.last_error ?? "Marcado manualmente como fallido." : null,
                sent_at: status === "sent" ? new Date().toISOString() : item.sent_at,
                next_attempt_at: status === "sent" || status === "failed" ? null : item.next_attempt_at
              }
            : item
        )
      }));
    } catch {
      setData(demoDashboardData);
      setLoadState((current) => ({
        ...current,
        error: "No se pudo actualizar el delivery. Se mantuvo la vista local."
      }));
    }
  }

  return (
    <section className="grid gap-6">
      <div className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="grid gap-2">
          <h1 className="text-2xl font-semibold tracking-normal text-white">Panel operativo</h1>
          <p className="max-w-2xl text-sm leading-6 text-slate-400">
            Entregas, alertas y reintentos de salida para analistas y soporte interno.
          </p>
        </div>
        <button
          type="button"
          className="focus-ring inline-flex h-10 items-center gap-2 rounded-md border border-border bg-panel px-4 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
          onClick={() => {
            setLoadState((current) => ({ ...current, loading: true }));
            void fetchDashboardData()
              .then((nextData) => {
                setData(nextData);
                setLoadState({ loading: false, error: null, demo: false });
              })
              .catch((error) => {
                setData(demoDashboardData);
                setLoadState({
                  loading: false,
                  error:
                    error instanceof DashboardAuthError
                      ? "Vista publica de muestra. Inicia sesion como admin/analista para ver indicadores reales."
                      : error instanceof Error
                        ? error.message
                        : "No se pudo cargar el panel.",
                  demo: true
                });
              });
          }}
        >
          <RefreshCw size={16} />
          Refrescar
        </button>
      </div>

      {loadState.error ? (
        <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <AlertTriangle className="mt-0.5 shrink-0" size={18} />
          <p>{loadState.error}</p>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Notificaciones" value={metrics.notifications_total} helper={`${metrics.notifications_unread} sin leer`} tone="neutral" />
        <MetricCard label="Deliveries" value={metrics.deliveries_total} helper={`${metrics.deliveries_due} listos para reintento`} tone="neutral" />
        <MetricCard label="Enviados" value={metrics.deliveries_sent} helper="Deliverys cerrados correctamente" tone="success" />
        <MetricCard label="Fallidos" value={metrics.deliveries_failed} helper="Revisar ultimo error" tone="danger" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="rounded-md border border-border bg-panel p-6">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-white">Distribucion de deliveries</h2>
              <p className="mt-1 text-sm text-slate-400">Estado por canal con reintentos y fallos finales.</p>
            </div>
            <Filter className="text-slate-400" size={18} />
          </div>
          <div className="grid gap-3">
            {metrics.deliveries_by_channel.map((item) => (
              <div key={item.channel} className="grid gap-2 rounded-md border border-border bg-[#0a111d] p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-white">{item.channel}</span>
                  <StatusPill
                    label={`${formatMetricValue(item.total)} total`}
                    tone={item.failed > 0 ? "high" : item.pending > 0 || item.scheduled > 0 ? "medium" : "neutral"}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm text-slate-300 sm:grid-cols-4">
                  <Stat label="pending" value={item.pending} />
                  <Stat label="scheduled" value={item.scheduled} />
                  <Stat label="sent" value={item.sent} />
                  <Stat label="failed" value={item.failed} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-md border border-border bg-panel p-6">
          <h2 className="text-base font-semibold text-white">Ultimo fallo</h2>
          {metrics.last_failed_delivery ? (
            <div className="mt-4 grid gap-3 rounded-md border border-border bg-[#0a111d] p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-white">{metrics.last_failed_delivery.channel}</p>
                <StatusPill label={metrics.last_failed_delivery.status} tone="critical" />
              </div>
              <p className="text-sm text-slate-300">{metrics.last_failed_delivery.last_error}</p>
              <div className="grid gap-2 text-xs text-slate-400">
                <p>Intentos: {metrics.last_failed_delivery.attempts}</p>
                <p>Destino: {metrics.last_failed_delivery.destination ?? "Sin destino"}</p>
                <p>Creado: {new Date(metrics.last_failed_delivery.created_at).toLocaleString("es-PE")}</p>
              </div>
            </div>
          ) : (
            <p className="mt-4 text-sm text-slate-400">No hay fallos recientes.</p>
          )}
        </div>
      </div>

      <div className="rounded-md border border-border bg-panel p-6">
        <div className="flex flex-col gap-4 border-b border-border pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">Deliveries</h2>
            <p className="mt-1 text-sm text-slate-400">Filtra por estado o canal y ejecuta acciones manuales.</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Select label="Estado" value={statusFilter} options={deliveryStatuses} onChange={(value) => setStatusFilter(value)} />
            <Select label="Canal" value={channelFilter} options={deliveryChannels} onChange={(value) => setChannelFilter(value)} />
          </div>
        </div>

        <div className="mt-4 overflow-x-auto rounded-md border border-border">
          <table className="min-w-[860px] w-full border-collapse text-left text-sm">
            <thead className="border-b border-border bg-[#0a111d] text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Delivery</th>
                <th className="px-4 py-3 font-medium">Canal</th>
                <th className="px-4 py-3 font-medium">Estado</th>
                <th className="px-4 py-3 font-medium">Reintentos</th>
                <th className="px-4 py-3 font-medium">Siguiente</th>
                <th className="px-4 py-3 font-medium">Accion</th>
              </tr>
            </thead>
            <tbody>
              {filteredDeliveries.map((delivery) => (
                <tr key={delivery.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-4">
                    <div className="grid gap-1">
                      <p className="text-white">{delivery.notification_id}</p>
                      <p className="text-xs text-slate-400">{delivery.destination ?? "Sin destino"}</p>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-slate-300">{delivery.channel}</td>
                  <td className="px-4 py-4">
                    <StatusPill
                      label={delivery.status}
                      tone={delivery.status === "failed" ? "critical" : delivery.status === "sent" ? "neutral" : "high"}
                    />
                    {delivery.last_error ? <p className="mt-2 max-w-sm text-xs text-slate-400">{delivery.last_error}</p> : null}
                  </td>
                  <td className="px-4 py-4 text-slate-300">{delivery.attempts}</td>
                  <td className="px-4 py-4 text-slate-300">
                    {delivery.next_attempt_at ? new Date(delivery.next_attempt_at).toLocaleString("es-PE") : "N/A"}
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-2">
                      <ActionButton
                        icon={CheckCircle2}
                        label="Sent"
                        onClick={() => handleMarkStatus(delivery, "sent")}
                        disabled={delivery.status === "sent"}
                      />
                      <ActionButton
                        icon={XCircle}
                        label="Failed"
                        onClick={() => handleMarkStatus(delivery, "failed")}
                        disabled={delivery.status === "failed"}
                      />
                    </div>
                  </td>
                </tr>
              ))}
              {filteredDeliveries.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-400">
                    No hay deliveries para los filtros seleccionados.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="mt-4 flex items-center gap-3 text-xs text-slate-400">
          <ArrowUpRight size={14} />
          <span>{loadState.loading ? "Cargando panel..." : "Panel listo para revision interna."}</span>
        </div>
      </div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  helper,
  tone
}: {
  label: string;
  value: number;
  helper: string;
  tone: "neutral" | "success" | "danger";
}) {
  const toneClass =
    tone === "success"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
      : tone === "danger"
        ? "border-red-500/30 bg-red-500/10 text-red-100"
        : "border-border bg-[#0a111d] text-white";

  return (
    <div className={`rounded-md border p-5 ${toneClass}`}>
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-3 text-3xl font-semibold">{formatMetricValue(value)}</p>
      <p className="mt-2 text-xs text-slate-400">{helper}</p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-[#0b1320] px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-medium text-white">{formatMetricValue(value)}</p>
    </div>
  );
}

function Select<T extends string>({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: T;
  options: T[];
  onChange: (value: T) => void;
}) {
  return (
    <label className="grid gap-2 text-xs uppercase tracking-wide text-slate-500">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
        className="focus-ring h-10 rounded-md border border-border bg-[#0a111d] px-3 text-sm text-white"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function ActionButton({
  icon: Icon,
  label,
  onClick,
  disabled
}: {
  icon: ComponentType<{ size?: number }>;
  label: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="focus-ring inline-flex h-9 items-center gap-2 rounded-md border border-border bg-[#0a111d] px-3 text-xs text-slate-200 transition hover:border-slate-500 hover:bg-[#172236] disabled:cursor-not-allowed disabled:opacity-40"
    >
      <Icon size={14} />
      {label}
    </button>
  );
}
