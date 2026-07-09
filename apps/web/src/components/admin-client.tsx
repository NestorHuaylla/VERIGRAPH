"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Clock3,
  Download,
  FileText,
  History,
  Loader2,
  Mail,
  Paperclip,
  RefreshCw,
  ShieldCheck,
  XCircle
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ApiError, apiFetch, apiGet, apiPatch, downloadApiFile } from "@/lib/api";
import type {
  AppealStatus,
  AppealResponse,
  AuditLogResponse,
  CaseDetailResponse,
  EvidenceResponse,
  ReportDetailResponse,
  ReportListItem,
  ReportStatusResponse,
  ReviewStatus,
  RiskLevel
} from "@/lib/verigraph-types";
import { StatusPill } from "@/components/status-pill";

const statusLabels: Record<ReviewStatus, string> = {
  pending: "Pendiente",
  suspect: "Sospechoso",
  confirmed: "Confirmado",
  false_positive: "Falso positivo",
  appeal: "Apelacion",
  archived: "Archivado"
};

const riskLabels: Record<RiskLevel, string> = {
  low: "Bajo",
  medium: "Medio",
  high: "Alto",
  critical: "Critico"
};

const appealStatusLabels: Record<AppealResponse["status"], string> = {
  pending: "Pendiente",
  under_review: "En revision",
  accepted: "Aceptada",
  rejected: "Rechazada"
};

const demoReports: ReportListItem[] = [
  {
    id: "demo-001",
    entity_id: null,
    entity_type: "domain",
    entity_value: "oferta-premium.example",
    entity_normalized_value: "oferta-premium.example",
    status: "pending",
    risk_score: 34,
    risk_level: "high",
    created_at: "2026-05-27T10:00:00Z"
  },
  {
    id: "demo-002",
    entity_id: null,
    entity_type: "phone",
    entity_value: "+51 999 999 999",
    entity_normalized_value: "+51999999999",
    status: "suspect",
    risk_score: 21,
    risk_level: "medium",
    created_at: "2026-05-27T09:30:00Z"
  }
];

type LoadState = {
  loading: boolean;
  error: string | null;
  demo: boolean;
};

type ReportDetailState = {
  loading: boolean;
  error: string | null;
  demo: boolean;
  report: ReportDetailResponse | null;
  evidence: EvidenceResponse[];
  auditLogs: AuditLogResponse[];
  appeals: AppealResponse[];
};

type ReportDetailBundle = Pick<ReportDetailState, "report" | "evidence" | "auditLogs" | "appeals">;

const emptyDetailState: ReportDetailState = {
  loading: false,
  error: null,
  demo: false,
  report: null,
  evidence: [],
  auditLogs: [],
  appeals: []
};

export function AdminClient() {
  const [reports, setReports] = useState<ReportListItem[]>(demoReports);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, error: null, demo: true });
  const [detailState, setDetailState] = useState<ReportDetailState>(emptyDetailState);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [analyzingEvidenceId, setAnalyzingEvidenceId] = useState<string | null>(null);
  const [resolvingAppealId, setResolvingAppealId] = useState<string | null>(null);
  const [creatingCaseForReportId, setCreatingCaseForReportId] = useState<string | null>(null);
  const [detailActionError, setDetailActionError] = useState<string | null>(null);
  const [detailActionMessage, setDetailActionMessage] = useState<string | null>(null);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [exportingPdfReportId, setExportingPdfReportId] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const hasReports = useMemo(() => reports.length > 0, [reports.length]);
  const selectedReport = useMemo(
    () => reports.find((report) => report.id === selectedReportId) ?? null,
    [reports, selectedReportId]
  );

  const loadReports = useCallback(async () => {
    setLoadState((current) => ({ ...current, loading: true }));
    try {
      const response = await apiGet<ReportListItem[]>("/api/v1/reports?limit=100");
      setReports(response);
      setSelectedReportId(null);
      setDetailState(emptyDetailState);
      setLoadState({ loading: false, error: null, demo: false });
    } catch (caughtError) {
      const detail =
        caughtError instanceof ApiError && caughtError.status === 401
          ? "Inicia sesion con usuario analyst/admin/legal para cargar reportes reales."
          : caughtError instanceof ApiError
            ? caughtError.detail
            : "No se pudo conectar con el API.";
      setReports(demoReports);
      setSelectedReportId(null);
      setDetailState(emptyDetailState);
      setLoadState({ loading: false, error: detail, demo: true });
    }
  }, []);

  const handleExportCsv = useCallback(async () => {
    setExportingCsv(true);
    setExportError(null);
    try {
      await downloadApiFile("/api/v1/reports/export/csv?limit=1000", "verigraph-reportes.csv");
    } catch (caughtError) {
      setExportError(
        caughtError instanceof ApiError
          ? caughtError.detail
          : "No se pudo generar el CSV. Verifica tu sesion e intenta de nuevo."
      );
    } finally {
      setExportingCsv(false);
    }
  }, []);

  const handleExportPdf = useCallback(async (report: ReportListItem) => {
    setExportingPdfReportId(report.id);
    setExportError(null);
    try {
      await downloadApiFile(
        `/api/v1/reports/${report.id}/export/pdf`,
        `verigraph-reporte-${report.id}.pdf`
      );
    } catch (caughtError) {
      setExportError(
        caughtError instanceof ApiError
          ? caughtError.detail
          : "No se pudo generar el PDF. Verifica tu sesion e intenta de nuevo."
      );
    } finally {
      setExportingPdfReportId(null);
    }
  }, []);

  const loadReportDetail = useCallback(
    async (report: ReportListItem) => {
      setSelectedReportId(report.id);
      setDetailActionError(null);
      setDetailActionMessage(null);

      if (loadState.demo || report.id.startsWith("demo-")) {
        const demoDetail = buildDemoReportDetailBundle(report);
        setDetailState({ loading: false, error: null, demo: true, ...demoDetail });
        return;
      }

      setDetailState({ ...emptyDetailState, loading: true });
      try {
        const [detail, evidence, auditLogs, appeals] = await Promise.all([
          apiGet<ReportDetailResponse>(`/api/v1/reports/${report.id}`),
          apiGet<EvidenceResponse[]>(`/api/v1/reports/${report.id}/evidence?limit=100`),
          apiGet<AuditLogResponse[]>(`/api/v1/reports/${report.id}/audit-logs?limit=100`),
          apiGet<AppealResponse[]>(`/api/v1/reports/${report.id}/appeals?limit=100`)
        ]);

        setDetailState({
          loading: false,
          error: null,
          demo: false,
          report: detail,
          evidence,
          auditLogs,
          appeals
        });
      } catch (caughtError) {
        const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo cargar el detalle del reporte.";
        setDetailState({ ...emptyDetailState, loading: false, error: detail });
      }
    },
    [loadState.demo]
  );

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  async function updateReportStatus(report: ReportListItem, status: ReviewStatus) {
    if (loadState.demo) {
      setReports((current) => current.map((item) => (item.id === report.id ? { ...item, status } : item)));
      setDetailState((current) => updateDemoDetailStatus(current, report.id, status));
      return;
    }

    setUpdatingId(report.id);
    try {
      await apiPatch<ReportStatusResponse>(`/api/v1/reports/${report.id}/status`, {
        status,
        reason: `Actualizacion desde panel web: ${statusLabels[status]}.`
      });
      setReports((current) => current.map((item) => (item.id === report.id ? { ...item, status } : item)));
      setLoadState((current) => ({ ...current, error: null }));

      if (selectedReportId === report.id) {
        await loadReportDetail({ ...report, status });
      }
    } catch (caughtError) {
      const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo actualizar el reporte.";
      setLoadState((current) => ({ ...current, error: detail }));
    } finally {
      setUpdatingId(null);
    }
  }

  async function analyzeEvidence(evidence: EvidenceResponse) {
    if (!selectedReport) {
      return;
    }

    if (detailState.demo) {
      setDetailActionError(null);
      setDetailActionMessage("Analisis demo completado. Se actualizaron metadata y auditoria local.");
      setDetailState((current) => updateDemoEvidenceAnalysis(current, evidence.id));
      return;
    }

    setAnalyzingEvidenceId(evidence.id);
    setDetailActionError(null);
    setDetailActionMessage(null);
    try {
      const response = await apiFetch(`/api/v1/reports/${evidence.report_id}/evidence/${evidence.id}/analyze`, {
        method: "POST"
      });
      if (!response.ok) {
        throw new Error(`API error ${response.status}`);
      }
      await loadReportDetail(selectedReport);
      setDetailActionMessage("Analisis de evidencia completado.");
    } catch (caughtError) {
      setDetailActionError(caughtError instanceof Error ? caughtError.message : "No se pudo analizar la evidencia.");
    } finally {
      setAnalyzingEvidenceId(null);
    }
  }

  async function updateAppealStatus(appeal: AppealResponse, status: AppealStatus) {
    if (!selectedReport) {
      return;
    }

    const reason = `Revision desde panel web: ${appealStatusLabels[status]}.`;

    if (detailState.demo) {
      setDetailActionError(null);
      setDetailActionMessage(`Apelacion demo actualizada: ${appealStatusLabels[status]}.`);
      setDetailState((current) => updateDemoAppealStatus(current, appeal.id, status, reason));
      return;
    }

    setResolvingAppealId(appeal.id);
    setDetailActionError(null);
    setDetailActionMessage(null);
    try {
      await apiPatch(`/api/v1/appeals/${appeal.id}/status`, {
        status,
        reason
      });
      await loadReportDetail(selectedReport);
      setDetailActionMessage(`Apelacion actualizada: ${appealStatusLabels[status]}.`);
    } catch (caughtError) {
      const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo actualizar la apelacion.";
      setDetailActionError(detail);
    } finally {
      setResolvingAppealId(null);
    }
  }

  async function createCaseFromSelectedReport() {
    const report = detailState.report;
    if (!selectedReport || !report?.entity_id) {
      return;
    }

    if (detailState.demo) {
      setDetailActionError(null);
      setDetailActionMessage(`Expediente demo creado para ${report.entity_value ?? report.id}.`);
      setDetailState((current) => updateDemoCaseAuditLog(current));
      return;
    }

    setCreatingCaseForReportId(report.id);
    setDetailActionError(null);
    setDetailActionMessage(null);
    try {
      const caseDetail = await apiFetch(`/api/v1/entities/${report.entity_id}/case`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({})
      });
      if (!caseDetail.ok) {
        throw new Error(`API error ${caseDetail.status}`);
      }

      const createdCase = (await caseDetail.json()) as CaseDetailResponse;
      await loadReportDetail(selectedReport);
      setDetailActionMessage(`Expediente listo: ${createdCase.title} (${createdCase.id.slice(0, 8)}).`);
    } catch (caughtError) {
      setDetailActionError(caughtError instanceof Error ? caughtError.message : "No se pudo crear el expediente.");
    } finally {
      setCreatingCaseForReportId(null);
    }
  }

  return (
    <section className="grid gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Panel admin</h1>
          <p className="mt-2 text-sm text-slate-400">
            Revision de reportes, estados, evidencia, apelaciones y auditoria.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void handleExportCsv()}
            disabled={exportingCsv}
            className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-panel px-4 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {exportingCsv ? <Loader2 className="animate-spin" size={16} /> : <Download size={16} />}
            Exportar CSV
          </button>
          <button
            type="button"
            onClick={() => void loadReports()}
            className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-panel px-4 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
          >
            <RefreshCw className={loadState.loading ? "animate-spin" : ""} size={16} />
            Refrescar
          </button>
        </div>
      </div>

      {exportError ? (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          {exportError}
        </p>
      ) : null}

      {loadState.error ? (
        <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <AlertTriangle className="mt-0.5 shrink-0" size={18} />
          <p>
            {loadState.demo ? "Vista local activa. " : ""}
            {loadState.error}
          </p>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)]">
        <div className="overflow-x-auto rounded-md border border-border bg-panel">
          <table className="min-w-[860px] w-full border-collapse text-left text-sm">
            <thead className="border-b border-border bg-[#0a111d] text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">ID</th>
                <th className="px-4 py-3 font-medium">Entidad</th>
                <th className="px-4 py-3 font-medium">Estado</th>
                <th className="px-4 py-3 font-medium">Riesgo</th>
                <th className="px-4 py-3 font-medium">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr
                  key={report.id}
                  className={`border-b border-border last:border-0 ${
                    selectedReportId === report.id ? "bg-[#101a2b]" : ""
                  }`}
                >
                  <td className="px-4 py-4 text-slate-300">{report.id.slice(0, 8)}</td>
                  <td className="px-4 py-4">
                    <button
                      type="button"
                      className="focus-ring grid max-w-xs gap-1 rounded text-left"
                      onClick={() => void loadReportDetail(report)}
                    >
                      <span className="break-words text-white">{report.entity_value ?? "Sin entidad"}</span>
                      <span className="text-xs text-slate-400">{report.entity_type ?? "unknown"}</span>
                    </button>
                  </td>
                  <td className="px-4 py-4 text-slate-300">{statusLabels[report.status] ?? report.status}</td>
                  <td className="px-4 py-4">
                    {report.risk_level ? (
                      <StatusPill
                        label={`${riskLabels[report.risk_level]} ${report.risk_score ?? ""}`}
                        tone={report.risk_level}
                      />
                    ) : (
                      <StatusPill label="Sin score" tone="neutral" />
                    )}
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-2">
                      <ActionButton
                        label="Ver"
                        icon={FileText}
                        disabled={detailState.loading && selectedReportId === report.id}
                        onClick={() => void loadReportDetail(report)}
                      />
                      <ActionButton
                        label="Confirmar"
                        icon={CheckCircle2}
                        disabled={updatingId === report.id || report.status === "confirmed"}
                        onClick={() => void updateReportStatus(report, "confirmed")}
                      />
                      <ActionButton
                        label="Falso"
                        icon={XCircle}
                        disabled={updatingId === report.id || report.status === "false_positive"}
                        onClick={() => void updateReportStatus(report, "false_positive")}
                      />
                      <ActionButton
                        label="Archivar"
                        icon={Archive}
                        disabled={updatingId === report.id || report.status === "archived"}
                        onClick={() => void updateReportStatus(report, "archived")}
                      />
                      {updatingId === report.id ? <Loader2 className="mt-2 animate-spin text-slate-400" size={16} /> : null}
                    </div>
                  </td>
                </tr>
              ))}
              {!hasReports ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-slate-400">
                    No hay reportes para revisar.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <ReportDetailPanel
          state={detailState}
          selectedReport={selectedReport}
          actionError={detailActionError}
          analyzingEvidenceId={analyzingEvidenceId}
          resolvingAppealId={resolvingAppealId}
          creatingCase={creatingCaseForReportId === detailState.report?.id}
          onAnalyzeEvidence={(evidence) => void analyzeEvidence(evidence)}
          onUpdateAppealStatus={(appeal, status) => void updateAppealStatus(appeal, status)}
          onCreateCase={() => void createCaseFromSelectedReport()}
          actionMessage={detailActionMessage}
          onRefresh={selectedReport ? () => void loadReportDetail(selectedReport) : undefined}
          onExportPdf={selectedReport ? () => void handleExportPdf(selectedReport) : undefined}
          exportingPdf={selectedReport ? exportingPdfReportId === selectedReport.id : false}
        />
      </div>
    </section>
  );
}

function ReportDetailPanel({
  state,
  selectedReport,
  actionError,
  analyzingEvidenceId,
  resolvingAppealId,
  creatingCase,
  onAnalyzeEvidence,
  onUpdateAppealStatus,
  onCreateCase,
  actionMessage,
  onRefresh,
  onExportPdf,
  exportingPdf
}: {
  state: ReportDetailState;
  selectedReport: ReportListItem | null;
  actionError: string | null;
  analyzingEvidenceId: string | null;
  resolvingAppealId: string | null;
  creatingCase: boolean;
  onAnalyzeEvidence: (evidence: EvidenceResponse) => void;
  onUpdateAppealStatus: (appeal: AppealResponse, status: AppealStatus) => void;
  onCreateCase: () => void;
  actionMessage: string | null;
  onRefresh?: () => void;
  onExportPdf?: () => void;
  exportingPdf?: boolean;
}) {
  if (!selectedReport) {
    return (
      <aside className="rounded-md border border-border bg-panel p-6">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 text-slate-400" size={20} />
          <div>
            <h2 className="text-base font-semibold text-white">Detalle de revision</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              Selecciona un reporte para revisar motivo, evidencia, apelaciones y auditoria.
            </p>
          </div>
        </div>
      </aside>
    );
  }

  if (state.loading) {
    return (
      <aside className="grid min-h-[360px] place-items-center rounded-md border border-border bg-panel p-6 text-sm text-slate-300">
        <div className="flex items-center gap-3">
          <Loader2 className="animate-spin" size={18} />
          Cargando detalle
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

  if (!state.report) {
    return (
      <aside className="rounded-md border border-border bg-panel p-6 text-sm text-slate-400">
        No hay detalle cargado para este reporte.
      </aside>
    );
  }

  const report = state.report;

  return (
    <aside className="grid gap-4 rounded-md border border-border bg-panel p-5">
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-slate-500">Reporte {report.id.slice(0, 8)}</p>
          <h2 className="mt-1 break-words text-lg font-semibold text-white">{report.entity_value ?? "Sin entidad"}</h2>
          <p className="mt-1 break-words text-xs text-slate-400">{report.entity_normalized_value ?? "Sin normalizar"}</p>
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <StatusPill label={statusLabels[report.status]} tone="neutral" />
          {report.risk_level ? (
            <StatusPill label={`${riskLabels[report.risk_level]} ${report.risk_score ?? ""}`} tone={report.risk_level} />
          ) : (
            <StatusPill label="Sin score" tone="neutral" />
          )}
          {onExportPdf && !state.demo ? (
            <button
              type="button"
              onClick={onExportPdf}
              disabled={exportingPdf}
              className="focus-ring inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-border bg-[#101a2b] px-3 text-xs text-slate-200 transition hover:border-slate-500 hover:bg-[#172236] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {exportingPdf ? <Loader2 className="animate-spin" size={14} /> : <Download size={14} />}
              PDF
            </button>
          ) : null}
        </div>
      </div>

      {state.demo ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          Detalle local de desarrollo. Inicia sesion para revisar datos reales.
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

      <div className="grid gap-3 text-sm text-slate-300">
        <InfoRow icon={Clock3} label="Creado" value={formatDate(report.created_at)} />
        <InfoRow icon={Mail} label="Reportante" value={report.reporter_contact ?? "No informado"} />
        <InfoRow icon={FileText} label="Fuente" value={report.source} />
      </div>

      <Section title="Motivo reportado" icon={FileText}>
        <p className="whitespace-pre-wrap text-sm leading-6 text-slate-300">{report.reason}</p>
      </Section>

      <Section title="Expediente" icon={Archive}>
        <div className="grid gap-3">
          <p className="text-sm leading-6 text-slate-300">
            Convierte la entidad del reporte en un expediente operativo para agrupar reportes, evidencia, grafo y
            snapshot de riesgo.
          </p>
          {report.entity_id ? (
            <button
              type="button"
              disabled={creatingCase}
              onClick={onCreateCase}
              className="focus-ring inline-flex h-10 w-fit items-center justify-center gap-2 rounded-md border border-border bg-[#0a111d] px-4 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236] disabled:cursor-wait disabled:opacity-60"
            >
              {creatingCase ? <Loader2 className="animate-spin" size={16} /> : <Archive size={16} />}
              Crear o reutilizar expediente
            </button>
          ) : (
            <EmptyText text="Este reporte no tiene entidad asociada para crear expediente." />
          )}
        </div>
      </Section>

      <Section title="Score y senales" icon={ShieldCheck}>
        {report.risk_explanation ? <p className="mb-3 text-sm leading-6 text-slate-300">{report.risk_explanation}</p> : null}
        <div className="grid gap-2">
          {report.risk_signals.map((signal) => (
            <div key={`${signal.code}-${signal.weight}`} className="rounded-md border border-border bg-[#0a111d] px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-white">{signal.label}</p>
                <StatusPill label={`+${signal.weight}`} tone="neutral" />
              </div>
              <p className="mt-1 text-xs text-slate-500">{signal.code}</p>
            </div>
          ))}
          {report.risk_signals.length === 0 ? <EmptyText text="No hay senales de riesgo registradas." /> : null}
        </div>
      </Section>

      <Section title={`Evidencia (${state.evidence.length})`} icon={Paperclip}>
        <div className="grid gap-2">
          {state.evidence.map((evidence) => (
            <div key={evidence.id} className="rounded-md border border-border bg-[#0a111d] px-3 py-3">
              <p className="break-words text-sm text-white">{evidence.filename}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <ActionButton
                  label={analyzingEvidenceId === evidence.id ? "Analizando" : "Analizar"}
                  icon={analyzingEvidenceId === evidence.id ? Loader2 : ShieldCheck}
                  disabled={analyzingEvidenceId === evidence.id}
                  onClick={() => onAnalyzeEvidence(evidence)}
                />
              </div>
              <p className="mt-1 text-xs text-slate-400">
                {evidence.content_type ?? "unknown"} - {formatBytes(evidence.size_bytes)} - sha256 {evidence.sha256.slice(0, 12)}
              </p>
              <p className="mt-1 break-words text-xs text-slate-500">Objeto: {evidence.object_key}</p>
              <p className="mt-2 text-xs text-slate-500">Analisis: {getEvidenceAnalysisStatus(evidence)}</p>
            </div>
          ))}
          {state.evidence.length === 0 ? <EmptyText text="No hay evidencia registrada para este reporte." /> : null}
        </div>
      </Section>

      <Section title={`Apelaciones (${state.appeals.length})`} icon={AlertTriangle}>
        <div className="grid gap-2">
          {state.appeals.map((appeal) => (
            <div key={appeal.id} className="rounded-md border border-border bg-[#0a111d] px-3 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-white">{appealStatusLabels[appeal.status]}</p>
                <p className="text-xs text-slate-500">{formatDate(appeal.created_at)}</p>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-300">{appeal.reason}</p>
              {appeal.resolution_reason ? <p className="mt-2 text-xs text-slate-400">{appeal.resolution_reason}</p> : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <ActionButton
                  label="En revision"
                  icon={History}
                  disabled={resolvingAppealId === appeal.id || appeal.status === "under_review"}
                  onClick={() => onUpdateAppealStatus(appeal, "under_review")}
                />
                <ActionButton
                  label="Aceptar"
                  icon={CheckCircle2}
                  disabled={resolvingAppealId === appeal.id || appeal.status === "accepted"}
                  onClick={() => onUpdateAppealStatus(appeal, "accepted")}
                />
                <ActionButton
                  label="Rechazar"
                  icon={XCircle}
                  disabled={resolvingAppealId === appeal.id || appeal.status === "rejected"}
                  onClick={() => onUpdateAppealStatus(appeal, "rejected")}
                />
                {resolvingAppealId === appeal.id ? <Loader2 className="mt-2 animate-spin text-slate-400" size={16} /> : null}
              </div>
            </div>
          ))}
          {state.appeals.length === 0 ? <EmptyText text="No hay apelaciones asociadas." /> : null}
        </div>
      </Section>

      <Section title={`Auditoria (${state.auditLogs.length})`} icon={History}>
        <div className="grid gap-2">
          {state.auditLogs.map((auditLog) => (
            <div key={auditLog.id} className="rounded-md border border-border bg-[#0a111d] px-3 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-white">{auditLog.action}</p>
                <p className="text-xs text-slate-500">{formatDate(auditLog.created_at)}</p>
              </div>
              <p className="mt-1 text-xs text-slate-400">Actor: {auditLog.actor_user_id ?? "sistema/publico"}</p>
              <MetadataPreview metadata={auditLog.metadata} />
            </div>
          ))}
          {state.auditLogs.length === 0 ? <EmptyText text="No hay eventos de auditoria para este reporte." /> : null}
        </div>
      </Section>

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

function InfoRow({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <Icon className="mt-0.5 shrink-0 text-slate-500" size={15} />
      <p>
        <span className="text-slate-500">{label}: </span>
        <span>{value}</span>
      </p>
    </div>
  );
}

function MetadataPreview({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata).slice(0, 4);
  if (entries.length === 0) {
    return null;
  }

  return (
    <dl className="mt-3 grid gap-1 text-xs text-slate-400">
      {entries.map(([key, value]) => (
        <div key={key} className="grid grid-cols-[120px_minmax(0,1fr)] gap-2">
          <dt className="truncate text-slate-500">{key}</dt>
          <dd className="break-words">{formatMetadataValue(value)}</dd>
        </div>
      ))}
    </dl>
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

function buildDemoReportDetailBundle(report: ReportListItem): ReportDetailBundle {
  const detail: ReportDetailResponse = {
    id: report.id,
    entity_id: report.entity_id,
    entity_type: report.entity_type,
    entity_value: report.entity_value,
    entity_raw_value: report.entity_value,
    entity_normalized_value: report.entity_normalized_value,
    reporter_contact: "demo@verigraph.local",
    reason:
      "Reporte de desarrollo para validar el flujo de revision. La entidad comparte senales de pago urgente y datos de contacto reutilizados.",
    status: report.status,
    source: "demo_fallback",
    risk_score: report.risk_score,
    risk_level: report.risk_level,
    risk_explanation: "Score demo calculado por senales de texto y conexiones simuladas del grafo.",
    risk_signals: [
      { code: "urgent_payment", label: "Presion por pago rapido", weight: 5 },
      { code: "shared_contact", label: "Contacto reutilizado en reportes", weight: 4 }
    ],
    risk_rules_version: "demo",
    metadata: {
      entity_raw_value: report.entity_value,
      entity_normalized_value: report.entity_normalized_value,
      source: "demo"
    },
    created_at: report.created_at,
    updated_at: null
  };

  const evidence: EvidenceResponse[] = [
    {
      id: `${report.id}-evidence`,
      report_id: report.id,
      object_key: `demo/${report.id}/captura.png`,
      filename: "captura-demo.png",
      content_type: "image/png",
      size_bytes: 182400,
      sha256: "d0e0f0d0e0f0d0e0f0d0e0f0d0e0f0d0e0f0d0e0f0d0e0f0d0e0f0d0e0f0d0e0",
      metadata: {
        storage_status: "demo",
        analysis: {
          status: "queued",
          engine: "ocr",
          provider: "tesseract_stub"
        }
      },
      created_at: report.created_at
    }
  ];

  const auditLogs: AuditLogResponse[] = [
    {
      id: `${report.id}-audit-created`,
      actor_user_id: null,
      action: "report.created",
      target_type: "report",
      target_id: report.id,
      metadata: {
        entity_type: report.entity_type,
        risk_score: report.risk_score,
        risk_level: report.risk_level,
        source: "demo"
      },
      created_at: report.created_at
    }
  ];

  const appeals: AppealResponse[] = [
    {
      id: `${report.id}-appeal`,
      report_id: report.id,
      appellant_contact: "apelante@verigraph.local",
      reason:
        "Solicitud demo para validar el flujo de apelacion. El apelante indica que la entidad requiere una segunda revision.",
      status: "pending",
      resolution_reason: null,
      metadata: {
        source: "demo"
      },
      created_at: report.created_at,
      updated_at: null
    }
  ];

  return {
    report: detail,
    evidence,
    auditLogs,
    appeals
  };
}

function updateDemoDetailStatus(
  current: ReportDetailState,
  reportId: string,
  status: ReviewStatus
): ReportDetailState {
  if (!current.report || current.report.id !== reportId) {
    return current;
  }

  const now = new Date().toISOString();
  return {
    ...current,
    report: {
      ...current.report,
      status,
      updated_at: now,
      metadata: {
        ...current.report.metadata,
        last_status_reason: `Actualizacion desde panel web: ${statusLabels[status]}.`
      }
    },
    auditLogs: [
      ...current.auditLogs,
      {
        id: `${reportId}-audit-${now}`,
        actor_user_id: "demo-user",
        action: "report.status_changed",
        target_type: "report",
        target_id: reportId,
        metadata: {
          new_status: status,
          reason: `Actualizacion desde panel web: ${statusLabels[status]}.`
        },
        created_at: now
      }
    ]
  };
}

function updateDemoEvidenceAnalysis(current: ReportDetailState, evidenceId: string): ReportDetailState {
  if (!current.report) {
    return current;
  }

  const now = new Date().toISOString();
  return {
    ...current,
    evidence: current.evidence.map((evidence) =>
      evidence.id === evidenceId
        ? {
            ...evidence,
            metadata: {
              ...evidence.metadata,
              analysis: {
                status: "completed",
                engine: "demo_analysis",
                provider: "local_demo",
                relation_type: "mentioned_in_evidence",
                extracted_text: "Demo: se detecto un contacto y una promesa de pago urgente.",
                error: null,
                entities_created: 1,
                relations_created: 1
              }
            }
          }
        : evidence
    ),
    auditLogs: [
      ...current.auditLogs,
      {
        id: `${current.report.id}-audit-evidence-${now}`,
        actor_user_id: "demo-user",
        action: "evidence.analysis_completed",
        target_type: "report",
        target_id: current.report.id,
        metadata: {
          evidence_id: evidenceId,
          entities_created: 1,
          relations_created: 1
        },
        created_at: now
      }
    ]
  };
}

function updateDemoAppealStatus(
  current: ReportDetailState,
  appealId: string,
  status: AppealStatus,
  reason: string
): ReportDetailState {
  if (!current.report) {
    return current;
  }

  const now = new Date().toISOString();
  return {
    ...current,
    appeals: current.appeals.map((appeal) =>
      appeal.id === appealId
        ? {
            ...appeal,
            status,
            resolution_reason: reason,
            updated_at: now,
            metadata: {
              ...appeal.metadata,
              last_status_reason: reason
            }
          }
        : appeal
    ),
    auditLogs: [
      ...current.auditLogs,
      {
        id: `${current.report.id}-audit-appeal-${now}`,
        actor_user_id: "demo-user",
        action: "appeal.status_changed",
        target_type: "appeal",
        target_id: appealId,
        metadata: {
          report_id: current.report.id,
          new_status: status,
          reason
        },
        created_at: now
      }
    ]
  };
}

function updateDemoCaseAuditLog(current: ReportDetailState): ReportDetailState {
  if (!current.report) {
    return current;
  }

  const now = new Date().toISOString();
  return {
    ...current,
    auditLogs: [
      ...current.auditLogs,
      {
        id: `${current.report.id}-audit-case-${now}`,
        actor_user_id: "demo-user",
        action: "case.created",
        target_type: "case",
        target_id: `demo-case-${current.report.id}`,
        metadata: {
          report_id: current.report.id,
          root_entity_id: current.report.entity_id,
          root_entity_value: current.report.entity_value,
          source: "admin_demo"
        },
        created_at: now
      }
    ]
  };
}

function getEvidenceAnalysisStatus(evidence: EvidenceResponse): string {
  const analysis = evidence.metadata.analysis;
  if (typeof analysis !== "object" || analysis === null) {
    return "sin datos";
  }

  const status = (analysis as Record<string, unknown>).status;
  const engine = (analysis as Record<string, unknown>).engine;
  if (!status) {
    return "sin datos";
  }

  return engine ? `${String(status)} (${String(engine)})` : String(status);
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("es-PE");
}

function formatBytes(value: number | null): string {
  if (value === null) {
    return "tamano no informado";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatMetadataValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "N/A";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "[metadata]";
  }
}
