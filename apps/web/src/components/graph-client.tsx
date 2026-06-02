"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import type { Core, ElementDefinition, EventObject, LayoutOptions } from "cytoscape";
import {
  AlertTriangle,
  BarChart3,
  CircleDot,
  GitFork,
  Loader2,
  Maximize2,
  Network,
  RefreshCw,
  Sparkles,
  Users
} from "lucide-react";

import { ApiError, apiGet, apiPost } from "@/lib/api";
import type {
  GraphCommunitiesResponse,
  GraphCommunityResponse,
  GraphEdge,
  GraphEntityScore,
  GraphNode,
  GraphProjectionResponse,
  GraphResponse,
  GraphScoresResponse
} from "@/lib/verigraph-types";
import { StatusPill } from "@/components/status-pill";

const demoGraph: GraphResponse = {
  nodes: [
    { id: "telegram", label: "Telegram A", type: "social_channel" },
    { id: "domain", label: "dominio.com", type: "domain" },
    { id: "whatsapp", label: "WhatsApp", type: "phone" },
    { id: "wallet", label: "Wallet", type: "wallet" },
    { id: "report", label: "Reporte", type: "report" }
  ],
  edges: [
    { id: "e1", source: "telegram", target: "domain", type: "mentions", evidence: {} },
    { id: "e2", source: "domain", target: "whatsapp", type: "contact", evidence: {} },
    { id: "e3", source: "whatsapp", target: "wallet", type: "payment", evidence: {} },
    { id: "e4", source: "report", target: "domain", type: "reported", evidence: {} }
  ]
};

const nodeTypeLabels: Record<string, string> = {
  url: "URL",
  domain: "Dominio",
  phone: "Telefono",
  email: "Correo",
  wallet: "Wallet",
  social_profile: "Perfil social",
  social_channel: "Canal social",
  bank_account: "Cuenta bancaria",
  report: "Reporte",
  other: "Otro"
};

type GraphSelection =
  | {
      kind: "node";
      id: string;
      label: string;
      type: string;
      degree: number;
    }
  | {
      kind: "edge";
      id: string;
      source: string;
      target: string;
      type: string;
      evidence: Record<string, unknown>;
    };

type AnalyticsMode = "none" | "pagerank" | "degree" | "communities";

type AnalyticsState = {
  mode: AnalyticsMode;
  scores: GraphEntityScore[];
  communities: GraphCommunityResponse[];
  projection: GraphProjectionResponse | null;
};

const emptyAnalytics: AnalyticsState = {
  mode: "none",
  scores: [],
  communities: [],
  projection: null
};

const communityPalette = ["#22c55e", "#38bdf8", "#f59e0b", "#f472b6", "#a78bfa", "#14b8a6", "#f97316", "#e2e8f0"];

const graphStyle = [
  {
    selector: "core",
    style: {
      "selection-box-color": "#38bdf8",
      "selection-box-border-color": "#7dd3fc",
      "selection-box-opacity": 0.12
    }
  },
  {
    selector: "node",
    style: {
      label: "data(label)",
      width: "data(nodeSize)",
      height: "data(nodeSize)",
      "background-color": "#64748b",
      "border-width": 2,
      "border-color": "#94a3b8",
      color: "#e5e7eb",
      "font-size": 10,
      "font-weight": 600,
      "text-wrap": "wrap",
      "text-max-width": 110,
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 8,
      "overlay-opacity": 0
    }
  },
  {
    selector: "node[type = 'url'], node[type = 'domain']",
    style: {
      "background-color": "#1d4ed8",
      "border-color": "#93c5fd"
    }
  },
  {
    selector: "node[type = 'phone']",
    style: {
      "background-color": "#b45309",
      "border-color": "#fbbf24"
    }
  },
  {
    selector: "node[type = 'wallet'], node[type = 'bank_account']",
    style: {
      "background-color": "#b91c1c",
      "border-color": "#fca5a5"
    }
  },
  {
    selector: "node[type = 'email']",
    style: {
      "background-color": "#0f766e",
      "border-color": "#5eead4"
    }
  },
  {
    selector: "node[type = 'social_profile'], node[type = 'social_channel']",
    style: {
      "background-color": "#047857",
      "border-color": "#6ee7b7"
    }
  },
  {
    selector: "node[type = 'report']",
    style: {
      "background-color": "#475569",
      "border-color": "#cbd5e1"
    }
  },
  {
    selector: "node[communityColor]",
    style: {
      "border-color": "data(communityColor)",
      "border-width": 4
    }
  },
  {
    selector: "node[analyticsScore]",
    style: {
      "border-width": 4
    }
  },
  {
    selector: "edge",
    style: {
      label: "data(type)",
      width: 1.6,
      "curve-style": "bezier",
      "target-arrow-shape": "triangle",
      "target-arrow-color": "#94a3b8",
      "line-color": "#64748b",
      color: "#94a3b8",
      "font-size": 8,
      "text-background-color": "#0a111d",
      "text-background-opacity": 0.85,
      "text-background-padding": "2px",
      "text-rotation": "autorotate",
      "overlay-opacity": 0
    }
  },
  {
    selector: ":selected",
    style: {
      "border-width": 4,
      "border-color": "#f8fafc",
      "line-color": "#e2e8f0",
      "target-arrow-color": "#e2e8f0"
    }
  }
] as unknown as cytoscape.StylesheetJson;

export function GraphClient() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [graph, setGraph] = useState<GraphResponse>(demoGraph);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState(true);
  const [selection, setSelection] = useState<GraphSelection | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsState>(emptyAnalytics);
  const [analyticsLoading, setAnalyticsLoading] = useState<AnalyticsMode | "projection" | null>(null);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiGet<GraphResponse>("/api/v1/graph/preview?limit=100");
      setGraph(response);
      setError(null);
      setDemo(false);
      setSelection(null);
      setAnalytics((current) => ({ ...current }));
    } catch (caughtError) {
      const detail =
        caughtError instanceof ApiError && caughtError.status === 401
          ? "Inicia sesion con usuario analyst/admin/legal para cargar el grafo real."
          : caughtError instanceof ApiError
            ? caughtError.detail
            : "No se pudo conectar con el API.";
      setGraph(demoGraph);
      setError(detail);
      setDemo(true);
      setSelection(null);
      setAnalytics(emptyAnalytics);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  const elements = useMemo(() => buildCytoscapeElements(graph, analytics), [analytics, graph]);
  const nodeTypes = useMemo(() => summarizeNodeTypes(graph.nodes), [graph.nodes]);
  const activeScores = analytics.mode === "pagerank" || analytics.mode === "degree" ? analytics.scores : [];
  const activeCommunities = analytics.mode === "communities" ? analytics.communities : [];

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: graphStyle,
      minZoom: 0.2,
      maxZoom: 2.5,
      wheelSensitivity: 0.18,
      layout: buildLayoutOptions("cose")
    });

    cy.on("tap", "node", (event: EventObject) => {
      const node = event.target;
      const data = node.data() as { id: string; label: string; type: string };
      setSelection({
        kind: "node",
        id: data.id,
        label: data.label,
        type: data.type,
        degree: node.degree()
      });
    });

    cy.on("tap", "edge", (event: EventObject) => {
      const data = event.target.data() as {
        id: string;
        source: string;
        target: string;
        type: string;
        evidence?: Record<string, unknown>;
      };
      setSelection({
        kind: "edge",
        id: data.id,
        source: data.source,
        target: data.target,
        type: data.type,
        evidence: data.evidence ?? {}
      });
    });

    cy.on("tap", (event: EventObject) => {
      if (event.target === cy) {
        setSelection(null);
      }
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [elements]);

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }

    const resizeObserver = new ResizeObserver(() => {
      cyRef.current?.resize();
      cyRef.current?.fit(undefined, 32);
    });
    resizeObserver.observe(containerRef.current);

    return () => resizeObserver.disconnect();
  }, []);

  function runLayout(name: "cose" | "circle" | "grid") {
    cyRef.current?.layout(buildLayoutOptions(name, true)).run();
  }

  function fitGraph() {
    cyRef.current?.fit(undefined, 36);
  }

  async function loadProjection(refresh = true) {
    setAnalyticsLoading("projection");
    setAnalyticsError(null);
    try {
      const projection = await apiPost<GraphProjectionResponse>(`/api/v1/graph/analytics/projection?refresh=${refresh}`, {});
      setAnalytics((current) => ({ ...current, projection }));
    } catch (caughtError) {
      setAnalyticsError(formatApiError(caughtError, "No se pudo preparar la proyeccion GDS."));
    } finally {
      setAnalyticsLoading(null);
    }
  }

  async function loadScores(mode: "pagerank" | "degree") {
    setAnalyticsLoading(mode);
    setAnalyticsError(null);
    try {
      const response = await apiGet<GraphScoresResponse>(
        `/api/v1/graph/analytics/${mode}?limit=25&refresh_projection=false`
      );
      setAnalytics((current) => ({
        ...current,
        mode,
        scores: response.items,
        communities: []
      }));
    } catch (caughtError) {
      setAnalyticsError(formatApiError(caughtError, `No se pudo cargar ${mode === "pagerank" ? "PageRank" : "degree"}.`));
    } finally {
      setAnalyticsLoading(null);
    }
  }

  async function loadCommunities() {
    setAnalyticsLoading("communities");
    setAnalyticsError(null);
    try {
      const response = await apiGet<GraphCommunitiesResponse>(
        "/api/v1/graph/analytics/communities?limit=10&refresh_projection=false"
      );
      setAnalytics((current) => ({
        ...current,
        mode: "communities",
        scores: [],
        communities: response.communities
      }));
    } catch (caughtError) {
      setAnalyticsError(formatApiError(caughtError, "No se pudieron cargar las comunidades."));
    } finally {
      setAnalyticsLoading(null);
    }
  }

  return (
    <section className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="grid gap-5">
        <div className="rounded-md border border-border bg-panel p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold text-white">Vista de grafo</h1>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Exploracion visual de entidades, reportes y relaciones detectadas.
              </p>
            </div>
            <GitFork className="shrink-0 text-slate-400" size={24} />
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void loadGraph()}
              className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-[#0a111d] px-4 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
            >
              {loading ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
              Refrescar
            </button>
            <button
              type="button"
              onClick={fitGraph}
              className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border bg-[#0a111d] px-4 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
            >
              <Maximize2 size={16} />
              Ajustar
            </button>
          </div>

          {error ? (
            <div className="mt-5 flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              <AlertTriangle className="mt-0.5 shrink-0" size={18} />
              <p>
                {demo ? "Grafo demo activo. " : ""}
                {error}
              </p>
            </div>
          ) : null}
        </div>

        <div className="rounded-md border border-border bg-panel p-5">
          <h2 className="text-sm font-semibold text-white">Resumen</h2>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Metric label="Nodos" value={graph.nodes.length} />
            <Metric label="Aristas" value={graph.edges.length} />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {nodeTypes.map((item) => (
              <StatusPill key={item.type} label={`${nodeTypeLabels[item.type] ?? item.type}: ${item.count}`} tone="neutral" />
            ))}
          </div>
        </div>

        <div className="rounded-md border border-border bg-panel p-5">
          <h2 className="text-sm font-semibold text-white">Layout</h2>
          <div className="mt-4 grid grid-cols-3 gap-2">
            <LayoutButton label="Cose" onClick={() => runLayout("cose")} />
            <LayoutButton label="Circle" onClick={() => runLayout("circle")} />
            <LayoutButton label="Grid" onClick={() => runLayout("grid")} />
          </div>
        </div>

        <div className="rounded-md border border-border bg-panel p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-white">Analitica</h2>
            {analyticsLoading ? <Loader2 className="animate-spin text-slate-400" size={16} /> : <Sparkles className="text-slate-400" size={16} />}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <AnalyticsButton
              active={analytics.mode === "pagerank"}
              icon={<BarChart3 size={15} />}
              label="PageRank"
              loading={analyticsLoading === "pagerank"}
              onClick={() => void loadScores("pagerank")}
            />
            <AnalyticsButton
              active={analytics.mode === "degree"}
              icon={<Network size={15} />}
              label="Degree"
              loading={analyticsLoading === "degree"}
              onClick={() => void loadScores("degree")}
            />
            <AnalyticsButton
              active={analytics.mode === "communities"}
              icon={<Users size={15} />}
              label="Louvain"
              loading={analyticsLoading === "communities"}
              onClick={() => void loadCommunities()}
            />
            <AnalyticsButton
              active={false}
              icon={<RefreshCw size={15} />}
              label="GDS"
              loading={analyticsLoading === "projection"}
              onClick={() => void loadProjection(true)}
            />
          </div>
          <AnalyticsSummary analytics={analytics} scores={activeScores} communities={activeCommunities} />
          {analyticsError ? (
            <div className="mt-4 flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              <AlertTriangle className="mt-0.5 shrink-0" size={15} />
              <p>{analyticsError}</p>
            </div>
          ) : null}
        </div>

        <SelectionPanel selection={selection} graph={graph} />
      </aside>

      <div className="rounded-md border border-border bg-panel p-4">
        <div className="relative min-h-[560px] overflow-hidden rounded-md border border-border bg-[#070b12]">
          {graph.nodes.length === 0 ? (
            <div className="absolute inset-0 grid place-items-center text-sm text-slate-400">No hay nodos para mostrar.</div>
          ) : null}
          <div ref={containerRef} className="absolute inset-0" />
        </div>
      </div>
    </section>
  );
}

function buildCytoscapeElements(graph: GraphResponse, analytics: AnalyticsState): ElementDefinition[] {
  const scoreMap = new Map(analytics.scores.map((score) => [score.entity_id, score]));
  const scoreRange = getScoreRange(analytics.scores);
  const communityMap = buildCommunityMap(analytics.communities);

  return [
    ...graph.nodes.map((node) => {
      const score = scoreMap.get(node.id);
      const community = communityMap.get(node.id);
      return {
        data: {
          id: node.id,
          label: node.label,
          type: node.type,
          nodeSize: score ? scoreToNodeSize(score.score, scoreRange) : 44,
          analyticsScore: score?.score,
          communityId: community?.communityId,
          communityColor: community?.color
        },
        classes: node.type
      };
    }),
    ...graph.edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        evidence: edge.evidence
      }
    }))
  ];
}

function getScoreRange(scores: GraphEntityScore[]): { min: number; max: number } {
  if (scores.length === 0) {
    return { min: 0, max: 0 };
  }
  const values = scores.map((score) => score.score);
  return { min: Math.min(...values), max: Math.max(...values) };
}

function scoreToNodeSize(score: number, range: { min: number; max: number }): number {
  if (range.max <= range.min) {
    return 58;
  }
  const normalized = (score - range.min) / (range.max - range.min);
  return Math.round(42 + normalized * 34);
}

function buildCommunityMap(communities: GraphCommunityResponse[]): Map<string, { communityId: number; color: string }> {
  const map = new Map<string, { communityId: number; color: string }>();
  communities.forEach((community, index) => {
    const color = communityPalette[index % communityPalette.length];
    for (const member of community.members) {
      map.set(member.entity_id, { communityId: community.community_id, color });
    }
  });
  return map;
}

function buildLayoutOptions(name: "cose" | "circle" | "grid", animate = false): LayoutOptions {
  if (name === "cose") {
    return {
      name,
      animate,
      fit: true,
      padding: 42,
      nodeRepulsion: 9000,
      idealEdgeLength: 110,
      edgeElasticity: 100,
      gravity: 0.25,
      numIter: 1200
    };
  }

  return {
    name,
    animate,
    fit: true,
    padding: 42
  };
}

function summarizeNodeTypes(nodes: GraphNode[]): Array<{ type: string; count: number }> {
  const counts = new Map<string, number>();
  for (const node of nodes) {
    counts.set(node.type, (counts.get(node.type) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count);
}

function SelectionPanel({ selection, graph }: { selection: GraphSelection | null; graph: GraphResponse }) {
  if (!selection) {
    return (
      <div className="rounded-md border border-border bg-panel p-5">
        <div className="flex items-start gap-3">
          <CircleDot className="mt-0.5 text-slate-400" size={18} />
          <div>
            <h2 className="text-sm font-semibold text-white">Seleccion</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">Haz click en un nodo o relacion para ver su contexto.</p>
          </div>
        </div>
      </div>
    );
  }

  if (selection.kind === "node") {
    const relatedEdges = graph.edges.filter((edge) => edge.source === selection.id || edge.target === selection.id);
    return (
      <div className="rounded-md border border-border bg-panel p-5">
        <h2 className="text-sm font-semibold text-white">Nodo seleccionado</h2>
        <div className="mt-4 grid gap-2 text-sm text-slate-300">
          <InfoRow label="Etiqueta" value={selection.label} />
          <InfoRow label="Tipo" value={nodeTypeLabels[selection.type] ?? selection.type} />
          <InfoRow label="Degree visual" value={String(selection.degree)} />
          <InfoRow label="Relaciones" value={String(relatedEdges.length)} />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border bg-panel p-5">
      <h2 className="text-sm font-semibold text-white">Relacion seleccionada</h2>
      <div className="mt-4 grid gap-2 text-sm text-slate-300">
        <InfoRow label="Tipo" value={selection.type} />
        <InfoRow label="Origen" value={selection.source} />
        <InfoRow label="Destino" value={selection.target} />
      </div>
      <MetadataPreview metadata={selection.evidence} />
    </div>
  );
}

function MetadataPreview({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata).slice(0, 5);
  if (entries.length === 0) {
    return <p className="mt-3 text-xs text-slate-500">Sin metadata de evidencia.</p>;
  }

  return (
    <dl className="mt-4 grid gap-1 text-xs text-slate-400">
      {entries.map(([key, value]) => (
        <div key={key} className="grid grid-cols-[90px_minmax(0,1fr)] gap-2">
          <dt className="truncate text-slate-500">{key}</dt>
          <dd className="break-words">{formatMetadataValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-[#0a111d] px-3 py-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-white">{value}</p>
    </div>
  );
}

function LayoutButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="focus-ring inline-flex h-9 items-center justify-center rounded-md border border-border bg-[#0a111d] px-3 text-xs text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
    >
      {label}
    </button>
  );
}

function AnalyticsButton({
  active,
  icon,
  label,
  loading,
  onClick
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  loading: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className={`focus-ring inline-flex h-9 items-center justify-center gap-2 rounded-md border px-3 text-xs transition disabled:cursor-not-allowed disabled:opacity-70 ${
        active
          ? "border-sky-400 bg-sky-500/15 text-sky-100"
          : "border-border bg-[#0a111d] text-slate-200 hover:border-slate-500 hover:bg-[#172236]"
      }`}
    >
      {loading ? <Loader2 className="animate-spin" size={15} /> : icon}
      {label}
    </button>
  );
}

function AnalyticsSummary({
  analytics,
  scores,
  communities
}: {
  analytics: AnalyticsState;
  scores: GraphEntityScore[];
  communities: GraphCommunityResponse[];
}) {
  if (analytics.mode === "none" && !analytics.projection) {
    return null;
  }

  return (
    <div className="mt-4 grid gap-3">
      {analytics.projection ? (
        <div className="grid grid-cols-2 gap-2">
          <Metric label="GDS nodos" value={analytics.projection.node_count} />
          <Metric label="GDS aristas" value={analytics.projection.relationship_count} />
        </div>
      ) : null}
      {scores.length > 0 ? (
        <div className="grid gap-2">
          {scores.slice(0, 5).map((score) => (
            <ScoreRow key={score.entity_id} score={score} />
          ))}
        </div>
      ) : null}
      {communities.length > 0 ? (
        <div className="grid gap-2">
          {communities.slice(0, 5).map((community, index) => (
            <CommunityRow key={community.community_id} community={community} color={communityPalette[index % communityPalette.length]} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ScoreRow({ score }: { score: GraphEntityScore }) {
  return (
    <div className="rounded-md border border-border bg-[#0a111d] px-3 py-2">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="min-w-0 truncate text-slate-200">{score.label || score.entity_id}</span>
        <span className="shrink-0 font-semibold text-sky-200">{score.score.toFixed(3)}</span>
      </div>
      <p className="mt-1 text-[11px] text-slate-500">{nodeTypeLabels[score.type] ?? score.type}</p>
    </div>
  );
}

function CommunityRow({ community, color }: { community: GraphCommunityResponse; color: string }) {
  return (
    <div className="rounded-md border border-border bg-[#0a111d] px-3 py-2">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="inline-flex min-w-0 items-center gap-2 text-slate-200">
          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
          Comunidad {community.community_id}
        </span>
        <span className="shrink-0 text-slate-400">{community.size}</span>
      </div>
      <p className="mt-1 truncate text-[11px] text-slate-500">
        {community.members
          .slice(0, 3)
          .map((member) => member.label || member.entity_id)
          .join(", ")}
      </p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <p>
      <span className="text-slate-500">{label}: </span>
      <span className="break-words">{value}</span>
    </p>
  );
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

function formatApiError(caughtError: unknown, fallback: string): string {
  if (caughtError instanceof ApiError) {
    if (caughtError.status === 401) {
      return "Inicia sesion con usuario analyst/admin/legal.";
    }
    return caughtError.detail;
  }
  return fallback;
}
