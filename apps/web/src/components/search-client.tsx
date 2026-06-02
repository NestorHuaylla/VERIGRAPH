"use client";

import { FormEvent, useMemo, useState } from "react";
import { AlertTriangle, Loader2, Search, ShieldAlert } from "lucide-react";

import { ApiError, apiGet, getApiBaseUrl } from "@/lib/api";
import type { EntityType, PublicRiskResponse, RiskLevel } from "@/lib/verigraph-types";
import { StatusPill } from "@/components/status-pill";

const entityOptions: Array<{ value: EntityType | ""; label: string }> = [
  { value: "", label: "Auto" },
  { value: "url", label: "URL" },
  { value: "domain", label: "Dominio" },
  { value: "phone", label: "Telefono" },
  { value: "email", label: "Correo" },
  { value: "wallet", label: "Wallet crypto" },
  { value: "social_profile", label: "Perfil social" },
  { value: "social_channel", label: "Canal social" },
  { value: "bank_account", label: "Cuenta bancaria" },
  { value: "other", label: "Otro" }
];

const riskLabels: Record<RiskLevel, string> = {
  low: "Riesgo bajo",
  medium: "Riesgo medio",
  high: "Riesgo alto",
  critical: "Riesgo critico"
};

const fallbackSignals = [
  "Dominio conectado a reportes previos",
  "Telefono compartido entre varias entidades",
  "Patron de ganancia garantizada detectado"
];

export function SearchClient() {
  const [value, setValue] = useState("");
  const [entityType, setEntityType] = useState<EntityType | "">("");
  const [result, setResult] = useState<PublicRiskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const endpointLabel = useMemo(() => getApiBaseUrl(), []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedValue = value.trim();
    if (trimmedValue.length < 2) {
      setError("Ingresa una entidad valida para analizar.");
      setResult(null);
      return;
    }

    const params = new URLSearchParams({ value: trimmedValue });
    if (entityType) {
      params.set("entity_type", entityType);
    }

    setLoading(true);
    setError(null);

    try {
      const response = await apiGet<PublicRiskResponse>(`/api/v1/entities/risk?${params.toString()}`);
      setResult(response);
    } catch (caughtError) {
      const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo conectar con el API.";
      setError(`${detail} API: ${endpointLabel}`);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
      <div className="rounded-md border border-border bg-panel p-6">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal text-white">Buscador de riesgo</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Consulta URL, dominio, telefono, correo, wallet o usuario para obtener un nivel de riesgo explicable.
            </p>
          </div>
          <ShieldAlert className="shrink-0 text-warning" size={28} />
        </div>
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <label className="grid gap-2 text-sm text-slate-300">
            Entidad a consultar
            <div className="grid gap-3 md:grid-cols-[180px_minmax(0,1fr)_auto]">
              <select
                className="focus-ring h-12 rounded-md border border-border bg-[#0a111d] px-4 text-white"
                value={entityType}
                onChange={(event) => setEntityType(event.target.value as EntityType | "")}
              >
                {entityOptions.map((option) => (
                  <option key={option.value || "auto"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <input
                className="focus-ring min-h-12 rounded-md border border-border bg-[#0a111d] px-4 text-white placeholder:text-slate-500"
                placeholder="https://ejemplo.com/oferta, +51..., wallet, correo..."
                value={value}
                onChange={(event) => setValue(event.target.value)}
              />
              <button
                type="submit"
                disabled={loading}
                className="focus-ring inline-flex min-h-12 items-center justify-center gap-2 rounded-md bg-accent px-5 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:cursor-wait disabled:opacity-70"
              >
                {loading ? <Loader2 className="animate-spin" size={18} /> : <Search size={18} />}
                Analizar
              </button>
            </div>
          </label>
        </form>

        {error ? (
          <div className="mt-4 flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            <AlertTriangle className="mt-0.5 shrink-0" size={18} />
            <p>{error}</p>
          </div>
        ) : null}
      </div>

      <aside className="rounded-md border border-border bg-panel p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-white">{result ? "Resultado" : "Resultado ejemplo"}</h2>
          <StatusPill label={result ? riskLabels[result.level] : "Riesgo alto"} tone={result?.level ?? "high"} />
        </div>
        <p className="text-sm leading-6 text-slate-400">
          {result
            ? result.explanation
            : "Esta entidad presenta senales de posible fraude segun reportes, patrones tecnicos y conexiones en el grafo."}
        </p>
        {result ? (
          <div className="mt-5 grid gap-2 rounded-md border border-border bg-[#0a111d] p-4 text-sm text-slate-300">
            <p>Normalizado: {result.normalized_value}</p>
            <p>Reportes relacionados: {result.related_reports}</p>
            <p>Score: {result.score}</p>
          </div>
        ) : null}
        <ul className="mt-5 grid gap-3">
          {(result?.signals.length ? result.signals.map((signal) => signal.label) : fallbackSignals).map((signal) => (
            <li key={signal} className="rounded-md border border-border bg-[#0a111d] px-4 py-3 text-sm text-slate-300">
              {signal}
            </li>
          ))}
        </ul>
      </aside>
    </section>
  );
}
