// Shared types mirroring Artha backend response shapes.
// All monetary values are in PAISE (integer). Never use floats for amounts.

export interface Owner {
  id: string;
  name: string;
  is_admin: boolean;
  has_pin: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  token: string;
  owner_id: string;
  name: string;
  is_admin: boolean;
}

export interface Account {
  id: string;
  owner_id: string;
  account_type: string;
  institution: string;
  nickname: string | null;
  is_active: boolean;
  created_at: string;
  balance_paise: number | null;
}

// ── Holdings ─────────────────────────────────────────────────────────────────

export interface Holding {
  id: string;
  account_id: string | null;
  asset_class: string;
  instrument_name: string;
  units: number | null;
  nav_paise: number | null;
  purchase_price_paise: number | null;
  current_value_paise: number | null;
  valuation_date: string | null;
  avg_cost_paise: number | null;
  pl_paise: number | null;
  pl_pct: number | null;
  xirr: number | null;
  day_change_pct: number | null;
}

// ── Net Worth ─────────────────────────────────────────────────────────────────

export interface MonthlyNetWorth {
  month: string;
  net_worth_paise: number;
  change_paise: number;
  change_pct: number | null;
}

export interface AssetCategory {
  label: string;
  value_paise: number;
  pct: number;
  delta_paise: number;
}

export interface NetWorthResponse {
  total_assets_paise: number;
  total_liabilities_paise: number;
  net_worth_paise: number;
  history: MonthlyNetWorth[];
  assets_by_category: AssetCategory[];
}

// ── Tax Data ──────────────────────────────────────────────────────────────────

export interface TaxDataRecord {
  id: string;
  fiscal_year: string;
  gross_income_paise: number | null;
  taxable_income_paise: number | null;
  tax_paid_paise: number | null;
  tds_paise: number | null;
  itr_filed: boolean;
  created_at: string;
}

export interface FinancialGoal {
  id: string;
  owner_id: string;
  goal_name: string;
  target_amount_paise: number;
  current_amount_paise: number;
  target_date: string | null;
  category: string | null;
  is_active: boolean;
  progress_pct: number;
  created_at: string;
  updated_at: string;
}

export interface ProfileScope {
  owner_id: string;
  scope: "PRIMARY" | "SPOUSE" | "DEPENDENT";
}

export interface UserProfile {
  id: string;
  owner_id: string;
  risk_appetite: "conservative" | "moderate" | "aggressive";
  age: number | null;
  is_family_scope: boolean;
  total_monthly_income_paise: number;
  income_sources_json: unknown[];
  emis_json: unknown[];
  preferences: Record<string, unknown>;
  scopes: ProfileScope[];
  created_at: string;
  updated_at: string;
}

export interface Transaction {
  id: string;
  owner_id: string;
  account_id: string;
  transaction_date: string;
  amount_paise: number;
  transaction_type: "CREDIT" | "DEBIT";
  category: string | null;
  description: string;
  merchant: string | null;
  fiscal_year: string;
  currency: string;
  created_at: string;
}

export interface FamilyMember {
  owner_id: string;
  name: string;
  role: "PRIMARY" | "SPOUSE" | "DEPENDENT";
  is_admin: boolean;
  created_at: string;
}

// ── Orchestrator ─────────────────────────────────────────────────────────────

export interface RecommendationRequest {
  owner_id: string;
  query: string;
}

// Shape of final_output from the Critic evaluator
// All confidence/penalty values are 0-1 fractions (normalised at the API boundary).
export interface CriticOutput {
  final_confidence: number;      // 0-1
  baseline_confidence: number;   // 0-1
  total_penalty: number;         // 0-1
  consistency_flags: Array<{
    agent_a: string;
    agent_b: string;
    message: string;
    severity: string;
  }>;
  schema_warnings: string[];
  gaps: string[];
  warnings: string[];
}

// Dispatched agent result as stored in agent_outputs_json
export interface DispatchedAgentOutput {
  agent_id: string;
  fallback_tier: string;
  error: string | null;
  response: {
    agent_id: string;
    confidence: number;
    data_tier: string;
    data_freshness_hours: number;
    result: Record<string, unknown>;
    warnings: string[];
    fallback_used: boolean;
    risk_level?: string;
  } | null;
}

// Plan steps as stored in plan_json
export interface PlanJson {
  plan_id: string;
  original_query: string;
  steps: Array<{
    agent_id: string;
    context: Record<string, unknown>;
    depends_on: string[];
  }>;
}

export interface RecommendationResponse {
  recommendation_id: string;
  final_confidence: number;
  state: string;
  warnings: string[];
  gaps: string[];
  final_output: CriticOutput;
  plan_json?: PlanJson;
  agent_outputs_json?: DispatchedAgentOutput[];
}

export interface RecommendationEventRequest {
  event_type: "SURFACED" | "ACCEPTED" | "REJECTED" | "MODIFIED";
  actor_user_id: string;
  payload?: Record<string, unknown>;
}

export interface RecommendationEventResponse {
  event_id: string;
  recommendation_id: string;
  event_type: string;
  current_state: string;
}

// ── Agent registry ────────────────────────────────────────────────────────────

export interface AgentStatus {
  agent_id: string;
  capabilities: string[];
  status: "HEALTHY" | "DEGRADED" | "DOWN";
  last_heartbeat: string | null;
  endpoint: string;
  scope: string;
}

// ── Ingestion ─────────────────────────────────────────────────────────────────

export interface IngestionRun {
  id: string;
  source: string;
  trigger_type: string;
  status: string;
  records_fetched: number;
  records_passed: number;
  records_quarantined: number;
  started_at: string;
  completed_at: string | null;
}

// ── Recommendation summary (user-scoped list) ─────────────────────────────────

export interface RecommendationSummary {
  id: string;
  query: string;
  composite_confidence: number;
  current_state: string;
  created_at: string;
}

// ── Admin ────────────────────────────────────────────────────────────────────

export interface AuditRecommendation {
  id: string;
  owner_id: string;
  query: string;
  composite_confidence: number;
  current_state: string;
  created_at: string;
  event_count: number;
}

export interface QuarantineRecord {
  id: string;
  failure_stage: string;
  failure_reasons: unknown[];
  raw_amount_text: string | null;
  raw_date_text: string | null;
  quarantine_status: string;
  created_at: string;
}

// ── Chat thread ──────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  /** User query text, or the extracted natural-language answer for assistant. */
  content: string;
  timestamp: string;
  recommendation_id?: string;
  /** Full orchestrator response stored on assistant messages. */
  response?: RecommendationResponse;
  error?: string;
}
