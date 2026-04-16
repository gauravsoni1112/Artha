/**
 * Typed API client for the Artha backend.
 *
 * All calls attach the X-Artha-Token header from localStorage.
 * The base URL is configured via NEXT_PUBLIC_API_URL (default: http://localhost:8000).
 */

import type {
  Account,
  AgentStatus,
  AuditRecommendation,
  FamilyMember,
  FinancialGoal,
  IngestionRun,
  Owner,
  QuarantineRecord,
  RecommendationEventRequest,
  RecommendationEventResponse,
  RecommendationRequest,
  RecommendationResponse,
  RecommendationSummary,
  TokenResponse,
  Transaction,
  UserProfile,
} from "@/lib/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Core fetcher
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("artha_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["X-Artha-Token"] = token;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }

  // 204 No Content
  if (res.status === 204) return undefined as unknown as T;

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const auth = {
  login: (owner_id: string, pin: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ owner_id, pin }),
    }),

  logout: () =>
    request<void>("/auth/logout", { method: "POST" }),

  me: () => request<{ owner_id: string; name: string; is_admin: boolean }>("/auth/me"),
};

// ---------------------------------------------------------------------------
// Owners
// ---------------------------------------------------------------------------

export const owners = {
  list: () => request<Owner[]>("/owners"),

  get: (id: string) => request<Owner>(`/owners/${id}`),

  create: (data: { name: string; is_admin?: boolean; pin?: string }) =>
    request<Owner>("/owners", { method: "POST", body: JSON.stringify(data) }),

  patch: (id: string, data: { name?: string; is_admin?: boolean }) =>
    request<Owner>(`/owners/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  setPin: (id: string, pin: string) =>
    request<void>(`/owners/${id}/pin`, { method: "POST", body: JSON.stringify({ pin }) }),

  listFamily: (id: string) => request<FamilyMember[]>(`/owners/${id}/family`),

  addFamilyMember: (id: string, data: { owner_id: string; role: string }) =>
    request<FamilyMember>(`/owners/${id}/family`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  removeFamilyMember: (id: string, memberId: string) =>
    request<void>(`/owners/${id}/family/${memberId}`, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

export const accounts = {
  list: (ownerId: string, includeInactive = false) =>
    request<Account[]>(
      `/owners/${ownerId}/accounts?include_inactive=${includeInactive}`
    ),

  create: (
    ownerId: string,
    data: { account_type: string; institution: string; nickname?: string; account_number?: string }
  ) =>
    request<Account>(`/owners/${ownerId}/accounts`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  patch: (ownerId: string, accountId: string, data: Partial<Account>) =>
    request<Account>(`/owners/${ownerId}/accounts/${accountId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deactivate: (ownerId: string, accountId: string) =>
    request<void>(`/owners/${ownerId}/accounts/${accountId}`, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Goals
// ---------------------------------------------------------------------------

export const goals = {
  list: (ownerId: string, includeInactive = false) =>
    request<FinancialGoal[]>(
      `/owners/${ownerId}/goals?include_inactive=${includeInactive}`
    ),

  create: (
    ownerId: string,
    data: {
      goal_name: string;
      target_amount_paise: number;
      current_amount_paise?: number;
      target_date?: string;
      category?: string;
    }
  ) =>
    request<FinancialGoal>(`/owners/${ownerId}/goals`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  patch: (ownerId: string, goalId: string, data: Partial<FinancialGoal>) =>
    request<FinancialGoal>(`/owners/${ownerId}/goals/${goalId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deactivate: (ownerId: string, goalId: string) =>
    request<void>(`/owners/${ownerId}/goals/${goalId}`, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export const profile = {
  get: (ownerId: string) => request<UserProfile>(`/owners/${ownerId}/profile`),

  create: (
    ownerId: string,
    data: { risk_appetite?: string; age?: number; total_monthly_income_paise?: number }
  ) =>
    request<UserProfile>(`/owners/${ownerId}/profile`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  patch: (
    ownerId: string,
    data: {
      risk_appetite?: string;
      age?: number;
      is_family_scope?: boolean;
      total_monthly_income_paise?: number;
      income_sources_json?: unknown[];
      emis_json?: unknown[];
      preferences?: Record<string, unknown>;
    }
  ) =>
    request<UserProfile>(`/owners/${ownerId}/profile`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};

// ---------------------------------------------------------------------------
// Transactions
// ---------------------------------------------------------------------------

export interface TransactionFilters {
  account_id?: string;
  category?: string;
  date_from?: string;
  date_to?: string;
  transaction_type?: "CREDIT" | "DEBIT";
  search?: string;
  limit?: number;
  offset?: number;
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const transactions = {
  list: (ownerId: string, filters: TransactionFilters = {}) =>
    request<Transaction[]>(
      `/owners/${ownerId}/transactions${buildQuery(filters as Record<string, string>)}`
    ),

  csvUrl: (ownerId: string, filters: TransactionFilters = {}) => {
    const params = buildQuery(filters as Record<string, string>);
    // Returns a URL the browser opens directly — the token must be injected by
    // the caller as an Authorization query param or via a fetch with custom headers.
    return `${BASE_URL}/owners/${ownerId}/transactions.csv${params}`;
  },
};

// ---------------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------------

export const orchestrator = {
  recommend: (data: RecommendationRequest) =>
    request<RecommendationResponse>("/orchestrator/recommendation", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  addEvent: (recommendationId: string, data: RecommendationEventRequest) =>
    request<RecommendationEventResponse>(
      `/orchestrator/recommendation/${recommendationId}/events`,
      { method: "POST", body: JSON.stringify(data) }
    ).then(r => ({ ...r, new_state: r.current_state })),

  listMine: (params: { state?: string; limit?: number; offset?: number } = {}) =>
    request<RecommendationSummary[]>(
      `/orchestrator/recommendations${buildQuery(params as Record<string, string>)}`
    ),
};

// ---------------------------------------------------------------------------
// Static data
// ---------------------------------------------------------------------------

export interface StaticDataResponse {
  run_id: string;
  status: string;
  records_passed: number;
  records_quarantined: number;
}

export const staticData = {
  addInsurance: (
    ownerId: string,
    data: {
      account_id: string;
      policy_name: string;
      insurer: string;
      policy_type: string;
      sum_assured_paise: number;
      annual_premium_paise: number;
      policy_start_date: string;
      policy_end_date?: string;
      nominees?: string[];
    }
  ) =>
    request<StaticDataResponse>(`/owners/${ownerId}/static-data/insurance`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  addRealEstate: (
    ownerId: string,
    data: {
      account_id: string;
      property_name: string;
      property_type: string;
      purchase_date: string;
      purchase_price_paise: number;
      current_value_paise: number;
      address?: string;
      loan_outstanding_paise?: number;
    }
  ) =>
    request<StaticDataResponse>(`/owners/${ownerId}/static-data/real-estate`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  addGold: (
    ownerId: string,
    data: {
      account_id: string;
      gold_type: string;
      purchase_date: string;
      quantity_grams: number;
      purchase_price_paise: number;
      current_value_paise: number;
      description?: string;
    }
  ) =>
    request<StaticDataResponse>(`/owners/${ownerId}/static-data/gold`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  addITR: (
    ownerId: string,
    data: {
      account_id: string;
      fiscal_year: string;
      gross_income_paise: number;
      taxable_income_paise: number;
      tax_paid_paise: number;
      tds_paise?: number;
      itr_filed?: boolean;
      deductions_80c_paise?: number;
      deductions_80d_paise?: number;
    }
  ) =>
    request<StaticDataResponse>(`/owners/${ownerId}/static-data/itr`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ---------------------------------------------------------------------------
// Ingestion
// ---------------------------------------------------------------------------

export const ingestion = {
  listRuns: (limit = 20) => request<IngestionRun[]>(`/ingestion-runs?limit=${limit}`),

  getRun: (id: string) => request<IngestionRun>(`/ingestion-runs/${id}`),

  triggerGmail: (ownerId: string) =>
    request<unknown>(`/ingest/GMAIL?owner_id=${ownerId}`, { method: "POST" }),

  triggerZerodha: (ownerId: string, accountId: string) =>
    request<unknown>(`/ingest/ZERODHA_API?owner_id=${ownerId}&account_id=${accountId}`, {
      method: "POST",
    }),
};

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export const admin = {
  auditLog: (params: { owner_id?: string; state?: string; limit?: number; offset?: number } = {}) =>
    request<AuditRecommendation[]>(`/admin/audit-log${buildQuery(params as Record<string, string>)}`),

  ingestionRuns: (params: { source?: string; status?: string; limit?: number } = {}) =>
    request<IngestionRun[]>(`/admin/ingestion-runs${buildQuery(params as Record<string, string>)}`),

  agents: () => request<AgentStatus[]>("/admin/agents"),

  quarantine: (status = "PENDING_REVIEW") =>
    request<QuarantineRecord[]>(`/admin/quarantine?quarantine_status=${status}`),

  resolveQuarantine: (id: string, data: { quarantine_status: string; resolution_notes?: string }) =>
    request<void>(`/admin/quarantine/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
};
