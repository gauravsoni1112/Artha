"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useFamilyMembers } from "@/lib/queries";

export type ViewMode = "individual" | "family";

export const ARTHA_VIEW_KEY = "artha-view";

export function useViewMode(): { viewMode: ViewMode; isFamily: boolean } {
  const [viewMode, setViewMode] = useState<ViewMode>("individual");

  useEffect(() => {
    const stored = localStorage.getItem(ARTHA_VIEW_KEY) as ViewMode | null;
    if (stored === "individual" || stored === "family") setViewMode(stored);
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as ViewMode;
      if (detail === "individual" || detail === "family") setViewMode(detail);
    };
    window.addEventListener("artha-view-change", handler);
    return () => window.removeEventListener("artha-view-change", handler);
  }, []);

  return { viewMode, isFamily: viewMode === "family" };
}

// ── Time Range ────────────────────────────────────────────────────────────────

export type TimeRange = "1M" | "3M" | "FY" | "All";
export const ARTHA_TIMERANGE_KEY = "artha-timerange";
const TIMERANGE_EVENT = "artha-timerange-change";
const VALID_RANGES: TimeRange[] = ["1M", "3M", "FY", "All"];

/** Returns the start date of the current Indian fiscal year (April 1). */
export function getFYStart(): string {
  const now = new Date();
  const year = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  return `${year}-04-01`;
}

// Clamp to the 1st before subtracting months to avoid day-of-month overflow
// (e.g. March 31 - 1 month must not wrap to March 2 instead of February 1).
function subtractMonths(n: number): Date {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - n);
  return d;
}

/** Returns `{ date_from }` suitable for passing to the transactions API. */
export function getTimeRangeDates(range: TimeRange): { date_from?: string } {
  if (range === "All") return {};
  if (range === "FY") return { date_from: getFYStart() };
  return { date_from: subtractMonths(range === "1M" ? 1 : 3).toISOString().slice(0, 10) };
}

/** Returns the cutoff "YYYY-MM" string for filtering monthly history arrays. */
export function getTimeRangeCutoffMonth(range: TimeRange): string | undefined {
  if (range === "All") return undefined;
  if (range === "FY") return getFYStart().slice(0, 7);
  const d = subtractMonths(range === "1M" ? 1 : 3);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function useTimeRange(): { timeRange: TimeRange; setTimeRange: (r: TimeRange) => void } {
  const [timeRange, setTimeRangeState] = useState<TimeRange>("FY");

  useEffect(() => {
    const stored = localStorage.getItem(ARTHA_TIMERANGE_KEY) as TimeRange | null;
    if (stored && (VALID_RANGES as string[]).includes(stored)) setTimeRangeState(stored);
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<TimeRange>).detail;
      if ((VALID_RANGES as string[]).includes(detail)) setTimeRangeState(detail);
    };
    window.addEventListener(TIMERANGE_EVENT, handler);
    return () => window.removeEventListener(TIMERANGE_EVENT, handler);
  }, []);

  const setTimeRange = useCallback((r: TimeRange) => {
    localStorage.setItem(ARTHA_TIMERANGE_KEY, r);
    setTimeRangeState(r);
    window.dispatchEvent(new CustomEvent(TIMERANGE_EVENT, { detail: r }));
  }, []);

  return { timeRange, setTimeRange };
}

/**
 * Returns the effective list of owner IDs to query based on the current view mode.
 * In individual mode: [currentOwnerId]. In family mode: [currentOwnerId, ...memberIds].
 * Returns [] while auth is still loading.
 */
export function useOwnerIds(): string[] {
  const { owner } = useAuth();
  const { isFamily } = useViewMode();
  const ownerId = owner?.owner_id;
  const { data: familyMembers } = useFamilyMembers(isFamily ? ownerId : undefined);
  if (!ownerId) return [];
  if (!isFamily) return [ownerId];
  return [ownerId, ...(familyMembers?.map((m) => m.owner_id) ?? [])];
}
