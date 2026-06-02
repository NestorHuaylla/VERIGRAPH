"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Archive,
  CheckCircle2,
  Clock3,
  FileText,
  GitFork,
  Loader2,
  RefreshCw,
  ShieldCheck
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ApiError, apiFetch, apiGet, apiPatch } from "@/lib/api";
import type {
  CaseDetailResponse,
  CaseListItem,
  CaseStatus,
  CaseStatusResponse,
  CaseSyncResponse,
  RiskLevel
} from "@/lib/verigraph-types";
import { StatusPill } from "@/components/status-pill";

const caseStatusLabels: Record<CaseStatus, string> = {
  open: "Abierto",
  in_review: "En revision",
  resolved: "Resuelto",
  archived: "Archivado"
};

const riskLabels: Record<RiskLevel, string> = {
  low: "Bajo",
  medium: "Medio",
  high: "Alto",
  critical: "Critico"
};

const demoCases: CaseListItem[] = [
  {
    id: "demo-case-001",
    title: "domain: oferta-premium.example",
    summary: "Expediente demo con reportes conectados por dominio y telefono.",
    status: "open",
    risk_level: "high",
    root_entity_id: "demo-entity-domain",
    created_at: "2026-05-27T11:00:00Z",
    updated_at: null
  },
  {
    id: "demo-case-002",
    title: "phone: +51999999999",
    summary: "Entidad recurrente en reportes de pagos urgentes.",
    status: "in_review",
    risk_level: "medium",
    root_entity_id: "demo-entity-phone",
    created_at: "2026-05-27T12:30:00Z",
    updated_at: null
  }
];

type LoadState = {
  loading: boolean;
  error: string | null;
  demo: boolean;
};

type DetailState = {
  loading: boolean;
  error: string | null;
  demo: boolean;
  caseDetail: CaseDetailResponse | null;
};

const emptyDetailState: DetailState = {
  loading: false,
  error: null,
  demo: false,
  caseDetail: null
};

export function CasesClient() {
  const [cases, setCases] = useState<CaseListItem[]>(demoCases);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, error: null, demo: true });
  const [detailState, setDetailState] = useState<DetailState>(emptyDetailState);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [updatingCaseId, setUpdatingCaseId] = useState<string | null>(null);
  const [syncingCaseId, setSyncingCaseId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const selectedCase = useMemo(
    () => cases.find((caseItem) => caseItem.id === selectedCaseId) ?? null,
    [cases, selectedCaseId]
  );

  const loadCases = useCallback(async () => {
    setLoadState((current) => ({ ...current, loading: true }));
    setActionError(null);
    setActionMessage(null);

    try {
      const response = await apiGet<CaseListItem[]>("/api/v1/cases?limit=100");
      setCases(response);
      setSelectedCaseId(null);
      setDetailState(emptyDetailState);
      setLoadState({ loading: false, error: null, demo: false });
    } catch (caughtError) {
      const detail =
        caughtError instanceof ApiError && caughtError.status === 401
          ? "Inicia sesion con usuario analyst/admin/legal para cargar expedientes reales."
          : caughtError instanceof ApiError
            ? caughtError.detail
            : "No se pudo conectar con el API.";
      setCases(demoCases);
      setSelectedCaseId(null);
      setDetailState(emptyDetailState);
      setLoadState({ loading: false, error: detail, demo: true });
    }
  }, []);

  const loadCaseDetail = useCallback(
    async (caseItem: CaseListItem) => {
      setSelectedCaseId(caseItem.id);
      setActionError(null);
      setActionMessage(null);

      if (loadState.demo || caseItem.id.startsWith("demo-case-")) {
        setDetailState({
          loading: false,
          error: null,
          demo: true,
          caseDetail: buildDemoCaseDetail(caseItem)
        });
        return;
      }

      setDetailState({ ...emptyDetailState, loading: true });
      try {
        const detail = await apiGet<CaseDetailResponse>(`/api/v1/cases/${caseItem.id}`);
        setDetailState({ loading: false, error: null, demo: false, caseDetail: detail });
      } catch (caughtError) {
        const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo cargar el expediente.";
        setDetailState({ ...emptyDetailState, loading: false, error: detail });
      }
    },
    [loadState.demo]
  );

  useEffect(() => {
    void loadCases();
  }, [loadCases]);

  async function updateCaseStatus(caseItem: CaseListItem, status: CaseStatus) {
    const reason = `Actualizacion desde panel web: ${caseStatusLabels[status]}.`;

    if (loadState.demo) {
      setActionError(null);
      setActionMessage(`Estado demo actualizado: ${caseStatusLabels[status]}.`);
      setCases((current) =>
        current.map((item) => (item.id === caseItem.id ? { ...item, status, updated_at: new Date().toISOString() } : item))
      );
      setDetailState((current) => updateDemoCaseStatus(current, status, reason));
      return;
    }

    setUpdatingCaseId(caseItem.id);
    setActionError(null);
    setActionMessage(null);
    try {
      await apiPatch<CaseStatusResponse>(`/api/v1/cases/${caseItem.id}/status`, {
        status,
        reason
      });
      setCases((current) =>
        current.map((item) => (item.id === caseItem.id ? { ...item, status, updated_at: new Date().toISOString() } : item))
      );
      if (selectedCaseId === caseItem.id) {
        await loadCaseDetail({ ...caseItem, status });
      }
      setActionMessage(`Estado actualizado: ${caseStatusLabels[status]}.`);
    } catch (caughtError) {
      const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo actualizar el expediente.";
      setActionError(detail);
    } finally {
      setUpdatingCaseId(null);
    }
  }

  async function syncCaseSnapshot(caseItem: CaseListItem) {
    if (loadState.demo) {
      setActionError(null);
      setActionMessage("Snapshot demo sincronizado.");
      setDetailState((current) => syncDemoCaseSnapshot(current));
      return;
    }

    setSyncingCaseId(caseItem.id);
    setActionError(null);
    setActionMessage(null);
    try {
      const response = await apiFetch(`/api/v1/cases/${caseItem.id}/sync`, { method: "POST" });
      if (!response.ok) {
        throw new Error(`API error ${response.status}`);
      }
      const result = (await response.json()) as CaseSyncResponse;
      if (selectedCaseId === caseItem.id) {
        await loadCaseDetail(caseItem);
      }
      setActionMessage(result.message);
    } catch (caughtError) {
      setActionError(caughtError instanceof Error ? caughtError.message : "No se pudo sincronizar el expediente.");
    } finally {
      setSyncingCaseId(null);
    }
  }

  return (
    <section className="grid gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Expedientes</h1>
          <p className="mt-2 text-sm text-slate-400">
            Seguimiento operativo de entidades investigadas, reportes asociados, evidencia y grafo.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadCases()}
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

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(420px,1.05fr)]">
        <CasesTable
          cases={cases}
          selectedCaseId={selectedCaseId}
          updatingCaseId={updatingCaseId}
          syncingCaseId={syncingCaseId}
          onSelect={(caseItem) => void loadCaseDetail(caseItem)}
          onUpdateStatus={(caseItem, status) => void updateCaseStatus(caseItem, status)}
          onSync={(caseItem) => void syncCaseSnapshot(caseItem)}
        />
        <CaseDetailPanel
          state={detailState}
          selectedCase={selectedCase}
          actionError={actionError}
          actionMessage={actionMessage}
          syncing={Boolean(selectedCase && syncingCaseId === selectedCase.id)}
          onSync={selectedCase ? () => void syncCaseSnapshot(selectedCase) : undefined}
          onRefresh={selectedCase ? () => void loadCaseDetail(selectedCase) : undefined}
        />
      </div>
    </section>
  );
}

function CasesTable({
  cases,
  selectedCaseId,
  updatingCaseId,
  syncingCaseId,
  onSelect,
  onUpdateStatus,
  onSync
}: {
  cases: CaseListItem[];
  selectedCaseId: string | null;
  updatingCaseId: string | null;
  syncingCaseId: string | null;
  onSelect: (caseItem: CaseListItem) => void;
  onUpdateStatus: (caseItem: CaseListItem, status: CaseStatus) => void;
  onSync: (caseItem: CaseListItem) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-border bg-panel">
      <table className="min-w-[820px] w-full border-collapse text-left text-sm">
        <thead className="border-b border-border bg-[#0a111d] text-slate-400">
          <tr>
            <th className="px-4 py-3 font-medium">Expediente</th>
            <th className="px-4 py-3 font-medium">Estado</th>
            <th className="px-4 py-3 font-medium">Riesgo</th>
            <th className="px-4 py-3 font-medium">Actualizado</th>
            <th className="px-4 py-3 font-medium">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((caseItem) => (
            <tr
              key={caseItem.id}
              className={`border-b border-border last:border-0 ${selectedCaseId === caseItem.id ? "bg-[#101a2b]" : ""}`}
            >
              <td className="px-4 py-4">
                <button type="button" className="focus-ring grid max-w-sm gap-1 rounded text-left" onClick={() => onSelect(caseItem)}>
                  <span className="break-words text-white">{caseItem.title}</span>
                  <span className="text-xs text-slate-400">{caseItem.root_entity_id ?? "sin entidad raiz"}</span>
                </button>
              </td>
              <td className="px-4 py-4 text-slate-300">{caseStatusLabels[caseItem.status]}</td>
              <td className="px-4 py-4">
                <StatusPill label={riskLabels[caseItem.risk_level]} tone={caseItem.risk_level} />
              </td>
              <td className="px-4 py-4 text-slate-300">{formatDate(caseItem.updated_at ?? caseItem.created_at)}</td>
              <td className="px-4 py-4">
                <div className="flex flex-wrap gap-2">
                  <ActionButton label="Ver" icon={FileText} disabled={false} onClick={() => onSelect(caseItem)} />
                  <ActionButton
                    label={syncingCaseId === caseItem.id ? "Sync" : "Sync"}
                    icon={syncingCaseId === caseItem.id ? Loader2 : RefreshCw}
                    disabled={syncingCaseId === caseItem.id}
                    onClick={() => onSync(caseItem)}
                  />
                  <ActionButton
                    label="Revision"
                    icon={Activity}
                    disabled={updatingCaseId === caseItem.id || caseItem.status === "in_review"}
                    onClick={() => onUpdateStatus(caseItem, "in_review")}
                  />
                  <ActionButton
                    label="Resolver"
                    icon={CheckCircle2}
                    disabled={updatingCaseId === caseItem.id || caseItem.status === "resolved"}
                    onClick={() => onUpdateStatus(caseItem, "resolved")}
                  />
                  <ActionButton
                    label="Archivar"
                    icon={Archive}
                    disabled={updatingCaseId === caseItem.id || caseItem.status === "archived"}
                    onClick={() => onUpdateStatus(caseItem, "archived")}
                  />
                  {updatingCaseId === caseItem.id ? <Loader2 className="mt-2 animate-spin text-slate-400" size={16} /> : null}
                </div>
              </td>
            </tr>
          ))}
          {cases.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-4 py-8 text-center text-sm text-slate-400">
                No hay expedientes para revisar.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function CaseDetailPanel({
  state,
  selectedCase,
  actionError,
  actionMessage,
  syncing,
  onSync,
  onRefresh
}: {
  state: DetailState;
  selectedCase: CaseListItem | null;
  actionError: string | null;
  actionMessage: string | null;
  syncing: boolean;
  onSync?: () => void;
  onRefresh?: () => void;
}) {
  if (!selectedCase) {
    return (
      <aside className="rounded-md border border-border bg-panel p-6">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 text-slate-400" size={20} />
          <div>
            <h2 className="text-base font-semibold text-white">Detalle de expediente</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              Selecciona un expediente para revisar su entidad raiz, reportes, evidencia y metricas de grafo.
            </p>
          </div>
        </div>
      </aside>
    );
  }

  if (state.loading) {
    return (
      <aside className="grid min-h-[420px] place-items-center rounded-md border border-border bg-panel p-6 text-sm text-slate-300">
        <div className="flex items-center gap-3">
          <Loader2 className="animate-spin" size={18} />
          Cargando expediente
        </div>
      </aside>
    );
  }

  if (state.error) {
    return (
      <aside className="rounded-md border border-border bg-panel p-6">
        <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <AlertTriangle className="mt-0.5 shrink-0" size={18} />
          <p>{state.error}</p>
        </div>
      </aside>
    );
  }

  if (!state.caseDetail) {
    return (
      <aside className="rounded-md border border-border bg-panel p-6 text-sm text-slate-400">
        No hay detalle cargado para este expediente.
      </aside>
    );
  }

  const caseDetail = state.caseDetail;
  const snapshot = readSnapshot(caseDetail);

  return (
    <aside className="grid gap-4 rounded-md border border-border bg-panel p-5">
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-slate-500">Expediente {caseDetail.id.slice(0, 8)}</p>
          <h2 className="mt-1 break-words text-lg font-semibold text-white">{caseDetail.title}</h2>
          <p className="mt-1 text-xs text-slate-400">Creado: {formatDate(caseDetail.created_at)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill label={caseStatusLabels[caseDetail.status]} tone="neutral" />
          <StatusPill label={riskLabels[caseDetail.risk_level]} tone={caseDetail.risk_level} />
        </div>
      </div>

      {state.demo ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          Detalle local de desarrollo. Inicia sesion para revisar expedientes reales.
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

      <Section title="Entidad raiz" icon={ShieldCheck}>
        {caseDetail.root_entity ? (
          <div className="grid gap-2 text-sm text-slate-300">
            <InfoRow label="Tipo" value={caseDetail.root_entity.type} />
            <InfoRow label="Valor" value={caseDetail.root_entity.display_value} />
            <InfoRow label="Normalizado" value={caseDetail.root_entity.normalized_value} />
          </div>
        ) : (
          <EmptyText text="No hay entidad raiz asociada." />
        )}
      </Section>

      <Section title="Snapshot" icon={Activity}>
        <div className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Metric label="Reportes" value={String(snapshot.reportsCount)} />
            <Metric label="Evidencia" value={String(caseDetail.evidence_count)} />
            <Metric label="Nodos grafo" value={String(snapshot.graphNodesCount)} />
            <Metric label="Aristas grafo" value={String(snapshot.graphEdgesCount)} />
          </div>
          <div className="flex flex-wrap gap-2">
            {onSync ? (
              <button
                type="button"
                onClick={onSync}
                disabled={syncing}
                className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-[#0a111d] px-4 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236] disabled:cursor-wait disabled:opacity-60"
              >
                {syncing ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
                Sincronizar snapshot
              </button>
            ) : null}
            {onRefresh ? (
              <button
                type="button"
                onClick={onRefresh}
                className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-[#0a111d] px-4 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
              >
                <RefreshCw size={16} />
                Recargar detalle
              </button>
            ) : null}
          </div>
        </div>
      </Section>

      <Section title="Grafo" icon={GitFork}>
        {caseDetail.graph_metrics ? (
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label="Degree" value={String(caseDetail.graph_metrics.degree)} />
            <Metric label="Entrantes" value={String(caseDetail.graph_metrics.incoming)} />
            <Metric label="Salientes" value={String(caseDetail.graph_metrics.outgoing)} />
          </div>
        ) : (
          <EmptyText text="No hay metricas de grafo disponibles." />
        )}
        <p className="text-xs text-slate-500">
          Nodos: {caseDetail.graph.nodes.length} - Aristas: {caseDetail.graph.edges.length}
        </p>
      </Section>

      <Section title={`Reportes asociados (${caseDetail.reports.length})`} icon={FileText}>
        <div className="grid gap-2">
          {caseDetail.reports.map((report) => (
            <div key={report.id} className="rounded-md border border-border bg-[#0a111d] px-3 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-white">Reporte {report.id.slice(0, 8)}</p>
                <p className="text-xs text-slate-500">{formatDate(report.created_at)}</p>
              </div>
              <p className="mt-1 text-xs text-slate-400">{report.status} - {report.source}</p>
              <p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-300">{report.reason}</p>
            </div>
          ))}
          {caseDetail.reports.length === 0 ? <EmptyText text="No hay reportes asociados a este expediente." /> : null}
        </div>
      </Section>
    </aside>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: React.ReactNode }) {
  return (
    <section className="grid gap-3 rounded-md border border-border bg-[#0b1320] p-4">
      <div className="flex items-center gap-2">
        <Icon className="text-slate-400" size={16} />
        <h3 className="text-sm font-semibold text-white">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <p>
      <span className="text-slate-500">{label}: </span>
      <span>{value}</span>
    </p>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-[#0a111d] px-3 py-2">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function EmptyText({ text }: { text: string }) {
  return <p className="rounded-md border border-border bg-[#0a111d] px-3 py-3 text-sm text-slate-400">{text}</p>;
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

function buildDemoCaseDetail(caseItem: CaseListItem): CaseDetailResponse {
  const rootEntityType = caseItem.title.startsWith("phone") ? "phone" : "domain";
  const rootValue = caseItem.title.replace(/^[^:]+:\s*/, "");

  return {
    id: caseItem.id,
    title: caseItem.title,
    summary: caseItem.summary,
    status: caseItem.status,
    risk_level: caseItem.risk_level,
    root_entity: {
      id: caseItem.root_entity_id ?? "demo-root",
      type: rootEntityType,
      display_value: rootValue,
      normalized_value: rootValue.toLowerCase()
    },
    reports: [
      {
        id: `${caseItem.id}-report-001`,
        status: "pending",
        reason: "Reporte demo asociado a la entidad raiz con senales de pago urgente y contacto reutilizado.",
        source: "demo",
        created_at: caseItem.created_at
      }
    ],
    evidence_count: 1,
    graph: {
      nodes: [
        { id: caseItem.root_entity_id ?? "demo-root", label: rootValue, type: rootEntityType },
        { id: `${caseItem.id}-phone`, label: "+51999999999", type: "phone" }
      ],
      edges: [
        {
          id: `${caseItem.id}-edge`,
          source: caseItem.root_entity_id ?? "demo-root",
          target: `${caseItem.id}-phone`,
          type: "mentioned_in_report",
          evidence: { source: "demo" }
        }
      ]
    },
    graph_metrics: {
      entity_id: caseItem.root_entity_id ?? "demo-root",
      degree: 1,
      incoming: 0,
      outgoing: 1
    },
    metadata: {
      root_entity_id: caseItem.root_entity_id,
      snapshot: {
        reports_count: 1,
        evidence_count: 1,
        graph_nodes_count: 2,
        graph_edges_count: 1,
        graph_degree: 1,
        case_score: 26,
        case_risk_level: caseItem.risk_level
      }
    },
    created_at: caseItem.created_at,
    updated_at: caseItem.updated_at
  };
}

function updateDemoCaseStatus(current: DetailState, status: CaseStatus, reason: string): DetailState {
  if (!current.caseDetail) {
    return current;
  }

  return {
    ...current,
    caseDetail: {
      ...current.caseDetail,
      status,
      updated_at: new Date().toISOString(),
      metadata: {
        ...current.caseDetail.metadata,
        last_status_reason: reason
      }
    }
  };
}

function syncDemoCaseSnapshot(current: DetailState): DetailState {
  if (!current.caseDetail) {
    return current;
  }

  const snapshot = {
    reports_count: current.caseDetail.reports.length,
    evidence_count: current.caseDetail.evidence_count,
    graph_nodes_count: current.caseDetail.graph.nodes.length,
    graph_edges_count: current.caseDetail.graph.edges.length,
    graph_degree: current.caseDetail.graph_metrics?.degree ?? 0,
    case_score: current.caseDetail.risk_level === "critical" ? 42 : 28,
    case_risk_level: current.caseDetail.risk_level,
    synced_at: new Date().toISOString()
  };

  return {
    ...current,
    caseDetail: {
      ...current.caseDetail,
      metadata: {
        ...current.caseDetail.metadata,
        snapshot
      },
      updated_at: snapshot.synced_at
    }
  };
}

function readSnapshot(caseDetail: CaseDetailResponse) {
  const snapshot =
    typeof caseDetail.metadata.snapshot === "object" && caseDetail.metadata.snapshot !== null
      ? caseDetail.metadata.snapshot as Record<string, unknown>
      : {};
  return {
    reportsCount: numberFromUnknown(snapshot.reports_count, caseDetail.reports.length),
    graphNodesCount: numberFromUnknown(snapshot.graph_nodes_count, caseDetail.graph.nodes.length),
    graphEdgesCount: numberFromUnknown(snapshot.graph_edges_count, caseDetail.graph.edges.length)
  };
}

function numberFromUnknown(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("es-PE");
}
