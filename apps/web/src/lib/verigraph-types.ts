export type EntityType =
  | "url"
  | "domain"
  | "phone"
  | "email"
  | "wallet"
  | "social_profile"
  | "social_channel"
  | "bank_account"
  | "other";

export type RiskLevel = "low" | "medium" | "high" | "critical";
export type ReviewStatus = "pending" | "suspect" | "confirmed" | "false_positive" | "appeal" | "archived";
export type AppealStatus = "pending" | "under_review" | "accepted" | "rejected";
export type CaseStatus = "open" | "in_review" | "resolved" | "archived";
export type UserRole = "reporter" | "analyst" | "admin" | "legal";

export type RiskSignal = {
  code: string;
  label: string;
  weight: number;
};

export type PublicRiskResponse = {
  entity_type: EntityType;
  normalized_value: string;
  entity_id: string | null;
  related_reports: number;
  score: number;
  level: RiskLevel;
  explanation: string;
  signals: RiskSignal[];
  data_source: string;
};

export type ReportResponse = {
  id: string;
  entity_id: string;
  status: string;
  risk_score: number;
  risk_level: RiskLevel;
  message: string;
};

export type ReportListItem = {
  id: string;
  entity_id: string | null;
  entity_type: EntityType | null;
  entity_value: string | null;
  entity_normalized_value: string | null;
  status: ReviewStatus;
  risk_score: number | null;
  risk_level: RiskLevel | null;
  created_at: string;
};

export type ReportDetailResponse = {
  id: string;
  entity_id: string | null;
  entity_type: EntityType | null;
  entity_value: string | null;
  entity_raw_value: string | null;
  entity_normalized_value: string | null;
  reporter_contact: string | null;
  reason: string;
  status: ReviewStatus;
  source: string;
  risk_score: number | null;
  risk_level: RiskLevel | null;
  risk_explanation: string | null;
  risk_signals: RiskSignal[];
  risk_rules_version: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type ReportStatusResponse = {
  id: string;
  status: ReviewStatus;
  message: string;
};

export type EvidenceResponse = {
  id: string;
  report_id: string;
  object_key: string;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  sha256: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type AuditLogResponse = {
  id: string;
  actor_user_id: string | null;
  action: string;
  target_type: string;
  target_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type AppealResponse = {
  id: string;
  report_id: string;
  appellant_contact: string | null;
  reason: string;
  status: AppealStatus;
  resolution_reason: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    role: UserRole;
    is_active: boolean;
  };
};

export type UserListItem = {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
};

export type UserUpdateResponse = {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  message: string;
};

export type GraphNode = {
  id: string;
  label: string;
  type: string;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  evidence: Record<string, unknown>;
};

export type GraphResponse = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type GraphMetrics = {
  entity_id: string;
  degree: number;
  incoming: number;
  outgoing: number;
};

export type GraphProjectionResponse = {
  graph_name: string;
  node_count: number;
  relationship_count: number;
  created: boolean;
};

export type GraphEntityScore = {
  entity_id: string;
  label: string;
  type: string;
  score: number;
};

export type GraphScoresResponse = {
  items: GraphEntityScore[];
};

export type GraphCommunityMember = {
  entity_id: string;
  label: string;
  type: string;
};

export type GraphCommunityResponse = {
  community_id: number;
  size: number;
  members: GraphCommunityMember[];
};

export type GraphCommunitiesResponse = {
  communities: GraphCommunityResponse[];
};

export type CaseListItem = {
  id: string;
  title: string;
  summary: string | null;
  status: CaseStatus;
  risk_level: RiskLevel;
  root_entity_id: string | null;
  created_at: string;
  updated_at: string | null;
};

export type CaseEntityContext = {
  id: string;
  type: EntityType;
  display_value: string;
  normalized_value: string;
};

export type CaseReportItem = {
  id: string;
  status: string;
  reason: string;
  source: string;
  created_at: string;
};

export type CaseDetailResponse = {
  id: string;
  title: string;
  summary: string | null;
  status: CaseStatus;
  risk_level: RiskLevel;
  root_entity: CaseEntityContext | null;
  reports: CaseReportItem[];
  evidence_count: number;
  graph: GraphResponse;
  graph_metrics: GraphMetrics | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type CaseStatusResponse = {
  id: string;
  status: CaseStatus;
  message: string;
};

export type CaseSyncResponse = {
  id: string;
  snapshot: Record<string, unknown>;
  message: string;
};
