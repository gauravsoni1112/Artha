/**
 * TanStack Query hooks for Artha.
 */
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { accounts, admin, goals, holdings, ingestion, netWorth, orchestrator, owners, profile, staticData, taxData, transactions } from "@/lib/api";
import type { TransactionFilters } from "@/lib/api";
import type { RecommendationEventRequest, RecommendationRequest } from "@/lib/types";

// ── Profile ───────────────────────────────────────────────────────────────────

export function useProfile(ownerId: string | undefined) {
  return useQuery({
    queryKey: ["profile", ownerId],
    queryFn: () => profile.get(ownerId!),
    enabled: !!ownerId,
    staleTime: 60_000,
    retry: 1,
  });
}

// ── Accounts ──────────────────────────────────────────────────────────────────

export function useAccounts(ownerId: string | undefined) {
  return useQuery({
    queryKey: ["accounts", ownerId],
    queryFn: () => accounts.list(ownerId!),
    enabled: !!ownerId,
    staleTime: 60_000,
    retry: 1,
  });
}

// ── Goals ─────────────────────────────────────────────────────────────────────

export function useGoals(ownerId: string | undefined) {
  return useQuery({
    queryKey: ["goals", ownerId],
    queryFn: () => goals.list(ownerId!),
    enabled: !!ownerId,
    staleTime: 60_000,
    retry: 1,
  });
}

// ── Transactions ──────────────────────────────────────────────────────────────

export function useTransactions(
  ownerId: string | undefined,
  filters: TransactionFilters = {}
) {
  return useQuery({
    queryKey: ["transactions", ownerId, filters],
    queryFn: () => transactions.list(ownerId!, filters),
    enabled: !!ownerId,
    staleTime: 60_000,
    retry: 1,
  });
}

/** Transactions for the current calendar month (up to 500 rows). */
export function useCurrentMonthTransactions(ownerId: string | undefined) {
  const now = new Date();
  const dateFrom = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
  return useTransactions(ownerId, { date_from: dateFrom, limit: 500 });
}

// ── Holdings ──────────────────────────────────────────────────────────────────

export function useHoldings(ownerId: string | undefined) {
  return useQuery({
    queryKey: ["holdings", ownerId],
    queryFn: () => holdings.list(ownerId!),
    enabled: !!ownerId,
    staleTime: 60_000,
    retry: 1,
  });
}

// ── Net Worth ─────────────────────────────────────────────────────────────────

export function useNetWorth(ownerId: string | undefined) {
  return useQuery({
    queryKey: ["net-worth", ownerId],
    queryFn: () => netWorth.get(ownerId!),
    enabled: !!ownerId,
    staleTime: 60_000,
    retry: 1,
  });
}

// ── Tax Data ──────────────────────────────────────────────────────────────────

export function useTaxData(ownerId: string | undefined) {
  return useQuery({
    queryKey: ["tax-data", ownerId],
    queryFn: () => taxData.list(ownerId!),
    enabled: !!ownerId,
    staleTime: 60_000,
    retry: 1,
  });
}

// ── Goal mutations ────────────────────────────────────────────────────────────

export function useCreateGoal(ownerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      goal_name: string;
      target_amount_paise: number;
      current_amount_paise?: number;
      target_date?: string;
      category?: string;
    }) => goals.create(ownerId!, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["goals", ownerId] }),
  });
}

export function usePatchGoal(ownerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ goalId, data }: { goalId: string; data: Record<string, unknown> }) =>
      goals.patch(ownerId!, goalId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["goals", ownerId] }),
  });
}

export function useDeactivateGoal(ownerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (goalId: string) => goals.deactivate(ownerId!, goalId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["goals", ownerId] }),
  });
}

// ── Account mutations ─────────────────────────────────────────────────────────

export function useCreateAccount(ownerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { account_type: string; institution: string; nickname?: string; account_number?: string }) =>
      accounts.create(ownerId!, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts", ownerId] }),
  });
}

export function usePatchAccount(ownerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ accountId, data }: { accountId: string; data: Record<string, unknown> }) =>
      accounts.patch(ownerId!, accountId, data as Parameters<typeof accounts.patch>[2]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts", ownerId] }),
  });
}

export function useDeactivateAccount(ownerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (accountId: string) => accounts.deactivate(ownerId!, accountId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts", ownerId] }),
  });
}

// ── Profile mutations ─────────────────────────────────────────────────────────

export function useCreateProfile(ownerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof profile.create>[1]) => profile.create(ownerId!, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profile", ownerId] }),
  });
}

export function usePatchProfile(ownerId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof profile.patch>[1]) => profile.patch(ownerId!, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profile", ownerId] }),
  });
}

// ── Static data mutations ─────────────────────────────────────────────────────

export function useAddInsurance(ownerId: string | undefined) {
  return useMutation({
    mutationFn: (data: Parameters<typeof staticData.addInsurance>[1]) =>
      staticData.addInsurance(ownerId!, data),
  });
}

export function useAddRealEstate(ownerId: string | undefined) {
  return useMutation({
    mutationFn: (data: Parameters<typeof staticData.addRealEstate>[1]) =>
      staticData.addRealEstate(ownerId!, data),
  });
}

export function useAddGold(ownerId: string | undefined) {
  return useMutation({
    mutationFn: (data: Parameters<typeof staticData.addGold>[1]) =>
      staticData.addGold(ownerId!, data),
  });
}

export function useAddITR(ownerId: string | undefined) {
  return useMutation({
    mutationFn: (data: Parameters<typeof staticData.addITR>[1]) =>
      staticData.addITR(ownerId!, data),
  });
}

// ── Family ────────────────────────────────────────────────────────────────────

export function useFamilyMembers(ownerId: string | undefined) {
  return useQuery({
    queryKey: ["family", ownerId],
    queryFn: () => owners.listFamily(ownerId!),
    enabled: !!ownerId,
    staleTime: 60_000,
    retry: 1,
  });
}

// ── Multi-owner (family) aggregation hooks ────────────────────────────────────

export function useMultiOwnerAccounts(ownerIds: string[]) {
  const results = useQueries({
    queries: ownerIds.map((id) => ({
      queryKey: ["accounts", id],
      queryFn: () => accounts.list(id),
      staleTime: 60_000,
      retry: 1 as const,
    })),
  });
  return {
    data: results.flatMap((r) => r.data ?? []),
    isLoading: results.some((r) => r.isLoading),
  };
}

export function useMultiOwnerGoals(ownerIds: string[]) {
  const results = useQueries({
    queries: ownerIds.map((id) => ({
      queryKey: ["goals", id],
      queryFn: () => goals.list(id),
      staleTime: 60_000,
      retry: 1 as const,
    })),
  });
  return {
    data: results.flatMap((r) => r.data ?? []),
    isLoading: results.some((r) => r.isLoading),
  };
}

export function useMultiOwnerTransactions(ownerIds: string[], filters: TransactionFilters = {}) {
  const results = useQueries({
    queries: ownerIds.map((id) => ({
      queryKey: ["transactions", id, filters],
      queryFn: () => transactions.list(id, filters),
      staleTime: 60_000,
      retry: 1 as const,
    })),
  });
  return {
    data: results
      .flatMap((r) => r.data ?? [])
      .sort((a, b) => b.transaction_date.localeCompare(a.transaction_date)),
    isLoading: results.some((r) => r.isLoading),
  };
}

export function useMultiOwnerHoldings(ownerIds: string[]) {
  const results = useQueries({
    queries: ownerIds.map((id) => ({
      queryKey: ["holdings", id],
      queryFn: () => holdings.list(id),
      staleTime: 60_000,
      retry: 1 as const,
    })),
  });
  return {
    data: results.flatMap((r) => r.data ?? []),
    isLoading: results.some((r) => r.isLoading),
  };
}

export function useMultiOwnerNetWorth(ownerIds: string[]) {
  const results = useQueries({
    queries: ownerIds.map((id) => ({
      queryKey: ["net-worth", id],
      queryFn: () => netWorth.get(id),
      staleTime: 60_000,
      retry: 1 as const,
    })),
  });
  const isLoading = results.some((r) => r.isLoading);
  const loaded = results.map((r) => r.data).filter(Boolean) as NonNullable<(typeof results)[number]["data"]>[];

  if (loaded.length === 0) return { data: undefined, isLoading };

  const total_assets_paise = loaded.reduce((s, d) => s + d.total_assets_paise, 0);
  const total_liabilities_paise = loaded.reduce((s, d) => s + d.total_liabilities_paise, 0);
  const net_worth_paise = total_assets_paise - total_liabilities_paise;

  // Sum net worth per calendar month across all owners, then recompute change fields
  const monthMap = new Map<string, number>();
  for (const d of loaded) {
    for (const h of d.history) {
      monthMap.set(h.month, (monthMap.get(h.month) ?? 0) + h.net_worth_paise);
    }
  }
  const sortedMonths = Array.from(monthMap.entries()).sort(([a], [b]) => a.localeCompare(b));
  const history = sortedMonths.map(([month, nw], i) => {
    // First entry has no prior month — treat as no change (0) to avoid displaying full NW as a gain
    const prevNw = i > 0 ? sortedMonths[i - 1][1] : nw;
    const change_paise = i > 0 ? nw - prevNw : 0;
    const change_pct = i > 0 && prevNw > 0
      ? Math.round((change_paise / prevNw) * 1000) / 10
      : null;
    return { month, net_worth_paise: nw, change_paise, change_pct };
  });

  // Sum asset categories and delta by label, recompute percentages
  const catMap = new Map<string, { value_paise: number; delta_paise: number }>();
  for (const d of loaded) {
    for (const a of d.assets_by_category) {
      const existing = catMap.get(a.label) ?? { value_paise: 0, delta_paise: 0 };
      catMap.set(a.label, {
        value_paise: existing.value_paise + a.value_paise,
        delta_paise: existing.delta_paise + a.delta_paise,
      });
    }
  }
  const safeTotalAssets = total_assets_paise || 1;
  const assets_by_category = Array.from(catMap.entries()).map(([label, { value_paise, delta_paise }]) => ({
    label,
    value_paise,
    pct: Math.round((value_paise / safeTotalAssets) * 100),
    delta_paise,
  }));

  return { data: { total_assets_paise, total_liabilities_paise, net_worth_paise, history, assets_by_category }, isLoading };
}

// ── Advisory / History ────────────────────────────────────────────────────────

export function useIngestionRuns(limit = 50) {
  return useQuery({
    queryKey: ["ingestion-runs", limit],
    queryFn: () => ingestion.listRuns(limit),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useMyRecommendations(params: { state?: string; limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: ["my-recommendations", params],
    queryFn: () => orchestrator.listMine(params),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useAdminAuditLog(
  params: { owner_id?: string; state?: string; limit?: number; offset?: number } = {}
) {
  return useQuery({
    queryKey: ["admin-audit-log", params],
    queryFn: () => admin.auditLog(params),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useQuarantine(status = "PENDING_REVIEW") {
  return useQuery({
    queryKey: ["quarantine", status],
    queryFn: () => admin.quarantine(status),
    staleTime: 30_000,
    retry: 1,
  });
}

export function useResolveQuarantine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status, notes }: { id: string; status: string; notes?: string }) =>
      admin.resolveQuarantine(id, { quarantine_status: status, resolution_notes: notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quarantine"] });
    },
  });
}

// ── Orchestrator ──────────────────────────────────────────────────────────────

export function useAskArtha() {
  return useMutation({
    mutationFn: (data: RecommendationRequest) => orchestrator.recommend(data),
  });
}

export function useRecommendationEvent(recommendationId: string | null) {
  return useMutation({
    mutationFn: (data: RecommendationEventRequest) => {
      if (!recommendationId) throw new Error("No recommendation ID");
      return orchestrator.addEvent(recommendationId, data);
    },
  });
}
