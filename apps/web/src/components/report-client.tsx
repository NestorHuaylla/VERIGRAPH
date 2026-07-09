"use client";

import { ChangeEvent, FormEvent, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, UploadCloud } from "lucide-react";

import { ApiError, apiFetch, apiPost, fetchCurrentUser, getApiBaseUrl } from "@/lib/api";
import type { EntityType, EvidenceResponse, ReportResponse } from "@/lib/verigraph-types";
import { StatusPill } from "@/components/status-pill";

const entityOptions: Array<{ value: EntityType; label: string }> = [
  { value: "url", label: "URL" },
  { value: "domain", label: "Dominio" },
  { value: "phone", label: "Telefono / WhatsApp" },
  { value: "email", label: "Correo" },
  { value: "wallet", label: "Wallet crypto" },
  { value: "social_profile", label: "Usuario o pagina social" },
  { value: "social_channel", label: "Canal social" },
  { value: "bank_account", label: "Cuenta bancaria" },
  { value: "other", label: "Otro" }
];

type SubmitState = {
  loading: boolean;
  error: string | null;
  report: ReportResponse | null;
  evidence: EvidenceResponse | null;
  evidenceWarning: string | null;
};

const initialState: SubmitState = {
  loading: false,
  error: null,
  report: null,
  evidence: null,
  evidenceWarning: null
};

export function ReportClient() {
  const [entityType, setEntityType] = useState<EntityType>("url");
  const [entityValue, setEntityValue] = useState("");
  const [reason, setReason] = useState("");
  const [reporterContact, setReporterContact] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [state, setState] = useState<SubmitState>(initialState);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(event.target.files?.[0] ?? null);
  }

  async function uploadEvidence(reportId: string, file: File): Promise<EvidenceResponse> {
    const formData = new FormData();
    formData.set("file", file);
    formData.set("description", `Evidencia enviada desde el formulario publico: ${file.name}`);

    const response = await apiFetch(`/api/v1/reports/${reportId}/evidence/upload`, {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      const message = response.status === 401 ? "Inicia sesion para subir evidencia al reporte." : `API error ${response.status}`;
      throw new Error(message);
    }

    return response.json() as Promise<EvidenceResponse>;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedValue = entityValue.trim();
    const trimmedReason = reason.trim();
    const trimmedContact = reporterContact.trim();

    if (trimmedValue.length < 2) {
      setState({ ...initialState, error: "Ingresa el valor de la entidad sospechosa." });
      return;
    }

    if (trimmedReason.length < 10) {
      setState({ ...initialState, error: "Describe el motivo con al menos 10 caracteres." });
      return;
    }

    setState({ ...initialState, loading: true });

    try {
      const report = await apiPost<ReportResponse>("/api/v1/reports", {
        entity_type: entityType,
        entity_value: trimmedValue,
        reason: trimmedReason,
        reporter_contact: trimmedContact || null
      });

      let evidence: EvidenceResponse | null = null;
      let evidenceWarning: string | null = null;

      if (selectedFile) {
        if (await fetchCurrentUser()) {
          try {
            evidence = await uploadEvidence(report.id, selectedFile);
          } catch (caughtError) {
            evidenceWarning = caughtError instanceof Error ? caughtError.message : "El reporte fue creado, pero no se subio la evidencia.";
          }
        } else {
          evidenceWarning = "Reporte creado. Para subir el archivo de evidencia, inicia sesion y vuelve a enviarlo.";
        }
      }

      setState({ loading: false, error: null, report, evidence, evidenceWarning });
    } catch (caughtError) {
      const detail = caughtError instanceof ApiError ? caughtError.detail : "No se pudo conectar con el API.";
      setState({
        ...initialState,
        error: `${detail} API: ${getApiBaseUrl()}`
      });
    }
  }

  return (
    <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
      <div>
        <h1 className="text-2xl font-semibold text-white">Formulario de reporte</h1>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          Registra entidades sospechosas con evidencia y contexto para revision humana.
        </p>

        {state.report ? (
          <div className="mt-6 grid gap-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-100">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={18} />
              <p>{state.report.message}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusPill label={`Reporte ${state.report.id.slice(0, 8)}`} tone="neutral" />
              <StatusPill label={`Score ${state.report.risk_score}`} tone={state.report.risk_level} />
            </div>
            {state.evidence ? <p>Evidencia subida: {state.evidence.filename}</p> : null}
            {state.evidenceWarning ? <p className="text-amber-100">{state.evidenceWarning}</p> : null}
          </div>
        ) : null}
      </div>

      <form className="grid gap-4 rounded-md border border-border bg-panel p-6" onSubmit={handleSubmit}>
        <label className="grid gap-2 text-sm text-slate-300">
          Tipo de entidad
          <select
            className="focus-ring h-12 rounded-md border border-border bg-[#0a111d] px-4 text-white"
            value={entityType}
            onChange={(event) => setEntityType(event.target.value as EntityType)}
          >
            {entityOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-2 text-sm text-slate-300">
          Valor
          <input
            className="focus-ring h-12 rounded-md border border-border bg-[#0a111d] px-4 text-white"
            value={entityValue}
            onChange={(event) => setEntityValue(event.target.value)}
            placeholder="https://sitio.com/oferta o +51..."
          />
        </label>
        <label className="grid gap-2 text-sm text-slate-300">
          Contacto del reportante
          <input
            className="focus-ring h-12 rounded-md border border-border bg-[#0a111d] px-4 text-white"
            type="email"
            value={reporterContact}
            onChange={(event) => setReporterContact(event.target.value)}
            placeholder="correo opcional"
          />
        </label>
        <label className="grid gap-2 text-sm text-slate-300">
          Motivo
          <textarea
            className="focus-ring min-h-32 rounded-md border border-border bg-[#0a111d] px-4 py-3 text-white"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Explica que paso, donde lo viste y por que parece sospechoso."
          />
        </label>
        <input
          ref={fileInputRef}
          className="hidden"
          type="file"
          accept="application/pdf,image/jpeg,image/png,image/webp,text/plain"
          onChange={handleFileChange}
        />
        <button
          type="button"
          className="focus-ring inline-flex min-h-12 items-center justify-center gap-2 rounded-md border border-dashed border-slate-500 bg-[#0a111d] px-4 text-sm text-slate-300"
          onClick={() => fileInputRef.current?.click()}
        >
          <UploadCloud size={18} />
          {selectedFile ? selectedFile.name : "Adjuntar evidencia"}
        </button>
        {state.error ? (
          <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            <AlertTriangle className="mt-0.5 shrink-0" size={18} />
            <p>{state.error}</p>
          </div>
        ) : null}
        <button
          type="submit"
          disabled={state.loading}
          className="focus-ring inline-flex h-12 items-center justify-center gap-2 rounded-md bg-signal px-5 text-sm font-semibold text-[#062018] transition hover:bg-emerald-400 disabled:cursor-wait disabled:opacity-70"
        >
          {state.loading ? <Loader2 className="animate-spin" size={18} /> : null}
          Enviar reporte
        </button>
      </form>
    </section>
  );
}
