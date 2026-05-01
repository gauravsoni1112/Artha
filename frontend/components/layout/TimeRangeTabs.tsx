"use client";

import React from "react";
import { type TimeRange, useTimeRange } from "@/lib/viewmode";

const RANGES: TimeRange[] = ["1M", "3M", "FY", "All"];

export function TimeRangeTabs() {
  const { timeRange, setTimeRange } = useTimeRange();
  return (
    <div
      style={{
        display: "flex",
        gap: 2,
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 3,
      }}
    >
      {RANGES.map((r) => (
        <button
          key={r}
          onClick={() => setTimeRange(r)}
          style={{
            padding: "4px 12px",
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            cursor: "pointer",
            transition: "all 0.15s",
            fontFamily: "inherit",
            border: timeRange === r ? "1px solid var(--border-bright)" : "1px solid transparent",
            background: timeRange === r ? "var(--bg3)" : "none",
            color: timeRange === r ? "var(--cyan)" : "var(--text-2)",
          }}
        >
          {r}
        </button>
      ))}
    </div>
  );
}
