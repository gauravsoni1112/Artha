"use client";

import React, { useMemo, useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { Sparkline } from "@/components/charts/Sparkline";
import { Donut } from "@/components/charts/Donut";
import { useAuth } from "@/lib/auth";
import { useNetWorth } from "@/lib/queries";
import { formatINRShort } from "@/lib/format";

const ASSET_COLORS = [
  "oklch(0.76 0.16 195)",
  "oklch(0.73 0.16 145)",
  "oklch(0.6 0.12 270)",
  "oklch(0.76 0.16 65)",
  "oklch(0.82 0.14 80)",
  "oklch(0.66 0.18 25)",
];

const RANGES = ["3M", "6M", "FY", "All"] as const;

export default function NetWorthPage() {
  const { owner } = useAuth();
  const ownerId = owner?.owner_id;
  const { data: nwData, isLoading } = useNetWorth(ownerId);
  const [range, setRange] = useState<string>("FY");

  const fullHistory = nwData?.history ?? [];
  const assets = (nwData?.assets_by_category ?? []).map((a, i) => ({
    ...a,
    color: ASSET_COLORS[i % ASSET_COLORS.length],
  }));

  // Filter history by range selector
  const history = useMemo(() => {
    const monthsBack = range === "3M" ? 3 : range === "6M" ? 6 : range === "FY" ? 12 : Infinity;
    if (!isFinite(monthsBack)) return fullHistory;
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - monthsBack);
    const cutoffStr = `${cutoff.getFullYear()}-${String(cutoff.getMonth() + 1).padStart(2, "0")}`;
    return fullHistory.filter((h) => h.month >= cutoffStr);
  }, [fullHistory, range]);

  // Sparkline data — normalize to relative units for display
  const sparkData = useMemo(() => {
    if (history.length === 0) return [0, 0];
    const vals = history.map((h) => h.net_worth_paise / 1e7);
    return vals.length < 2 ? [0, ...vals] : vals;
  }, [history]);

  const sparkMonths = useMemo(() => history.map((h) => {
    const [y, m] = h.month.split("-");
    return new Date(Number(y), Number(m) - 1).toLocaleString("en-IN", { month: "short" });
  }), [history]);

  const nwPaise = nwData?.net_worth_paise ?? 0;
  const nwLabel = nwPaise > 0 ? formatINRShort(nwPaise) : "—";

  const lastTwo = history.slice(-2);
  const changePaise = lastTwo.length >= 2 ? lastTwo[1].net_worth_paise - lastTwo[0].net_worth_paise : 0;
  const changePct = lastTwo.length >= 2 && lastTwo[0].net_worth_paise > 0
    ? (changePaise / lastTwo[0].net_worth_paise) * 100
    : 0;

  // History rows for the table (most recent first)
  const historyRows = useMemo(() => {
    const rows = [...history].reverse();
    return rows.map((row) => {
      const up = row.change_paise >= 0;
      const [y, m] = row.month.split("-");
      const monthLabel = new Date(Number(y), Number(m) - 1).toLocaleString("en-IN", { month: "short", year: "2-digit" });
      return {
        month: monthLabel,
        nw: formatINRShort(row.net_worth_paise),
        change: `${row.change_paise >= 0 ? "+" : ""}${formatINRShort(Math.abs(row.change_paise))}`,
        pct: row.change_pct != null ? `${row.change_pct >= 0 ? "+" : ""}${row.change_pct.toFixed(1)}%` : "—",
        up,
      };
    });
  }, [history]);

  const donutSegments = assets
    .filter((a) => a.pct >= 1)
    .map((a) => ({ value: a.pct, color: a.color }));

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Net Worth"
        subtitle="Total assets minus liabilities · Live"
        live
        actions={
          <div style={{ display: "flex", gap: 2, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 3 }}>
            {RANGES.map((r) => (
              <button key={r} onClick={() => setRange(r)}
                style={{
                  padding: "3px 10px", borderRadius: 5,
                  border: r === range ? "1px solid var(--border-bright)" : "none",
                  background: r === range ? "var(--bg3)" : "none",
                  color: r === range ? "oklch(0.76 0.16 195)" : "var(--text-2)",
                  fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                }}
              >{r}</button>
            ))}
          </div>
        }
      />

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {isLoading && (
          <div style={{ fontSize: 13, color: "var(--text-3)", padding: "20px 0" }}>Loading net worth…</div>
        )}

        {!isLoading && (
          <>
            {/* Hero value */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 44, fontWeight: 500, color: "var(--text)", letterSpacing: "-0.04em", lineHeight: 1 }}>{nwLabel}</div>
              {changePaise !== 0 && (
                <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
                  <span style={{
                    background: `oklch(0.73 0.16 ${changePaise >= 0 ? 145 : 25} / 0.15)`,
                    color: `oklch(0.73 0.16 ${changePaise >= 0 ? 145 : 25})`,
                    padding: "3px 9px", borderRadius: 5, fontSize: 12, fontFamily: "JetBrains Mono, monospace"
                  }}>
                    {changePaise >= 0 ? "▲" : "▼"} {formatINRShort(Math.abs(changePaise))} ({changePct >= 0 ? "+" : ""}{changePct.toFixed(1)}%)
                  </span>
                  <span style={{ fontSize: 11, color: "var(--text-3)" }}>vs last month</span>
                </div>
              )}
              {nwPaise === 0 && !isLoading && (
                <div style={{ fontSize: 13, color: "var(--text-3)", marginTop: 8 }}>
                  No financial data yet. Ingest transactions and holdings to see your net worth.
                </div>
              )}
            </div>

            {/* Sparkline */}
            {history.length > 0 && (
              <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 20px", marginBottom: 14 }}>
                <Sparkline data={sparkData} color="oklch(0.76 0.16 195)" height={100} />
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
                  {sparkMonths.map((m, i) => (
                    <span key={i} style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{m}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Asset cards */}
            {assets.length > 0 && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginBottom: 14 }}>
                {assets.map((a) => (
                  <AssetCard
                    key={a.label}
                    label={a.label}
                    val={formatINRShort(a.value_paise)}
                    pct={a.pct}
                    color={a.color}
                    // delta_paise is always 0 from API — no historical holdings prices tracked yet
                    delta="—"
                    up={true}
                  />
                ))}
                {nwData && nwData.total_liabilities_paise > 0 && (
                  <AssetCard
                    label="Liabilities"
                    val={`−${formatINRShort(nwData.total_liabilities_paise)}`}
                    pct={nwData.total_assets_paise > 0
                      ? Math.round(nwData.total_liabilities_paise / nwData.total_assets_paise * 100)
                      : 100}
                    color="oklch(0.66 0.18 25)"
                    delta="—"
                    up={false}
                  />
                )}
              </div>
            )}

            {/* Allocation + History */}
            {(donutSegments.length > 0 || historyRows.length > 0) && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 10 }}>
                {donutSegments.length > 0 && (
                  <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 20px" }}>
                    <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 12 }}>Allocation</div>
                    <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                      <Donut size={90} segments={donutSegments} />
                      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                        {assets.filter((a) => a.pct >= 1).map((a) => (
                          <div key={a.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <div style={{ width: 6, height: 6, borderRadius: "50%", background: a.color, flexShrink: 0 }} />
                            <span style={{ fontSize: 11, color: "var(--text-2)" }}>{a.label}</span>
                            <span style={{ fontSize: 10, color: "var(--text-3)", marginLeft: "auto", fontFamily: "JetBrains Mono, monospace", paddingLeft: 8 }}>{a.pct}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {historyRows.length > 0 && (
                  <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 20px" }}>
                    <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 12 }}>Monthly History</div>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border)" }}>
                          {["Month", "Net Worth", "Change", "%"].map((h) => (
                            <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontSize: 10, color: "var(--text-3)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase" }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {historyRows.slice(0, 6).map((row, i) => (
                          <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                            <td style={{ padding: "7px 8px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>{row.month}</td>
                            <td style={{ padding: "7px 8px", fontSize: 12, color: "var(--text)", fontFamily: "JetBrains Mono, monospace" }}>{row.nw}</td>
                            <td style={{ padding: "7px 8px", fontSize: 12, color: row.up ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", fontFamily: "JetBrains Mono, monospace" }}>{row.change}</td>
                            <td style={{ padding: "7px 8px", fontSize: 12, color: row.up ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", fontFamily: "JetBrains Mono, monospace" }}>{row.pct}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function AssetCard({ label, val, pct, color, delta, up }: { label: string; val: string; pct: number; color: string; delta: string; up: boolean }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ background: "var(--surface)", border: `1px solid ${hovered ? "var(--border-bright)" : "var(--border)"}`, borderRadius: 10, padding: "12px 14px", cursor: "pointer", transition: "all 0.15s" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>{label}</span>
      </div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 18, color: "var(--text)", marginBottom: 4 }}>{val}</div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontSize: 11, color: delta === "—" ? "var(--text-3)" : up ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)", fontFamily: "JetBrains Mono, monospace" }}>{delta}</span>
        <span style={{ fontSize: 10, color: "var(--text-3)" }}>{pct}%</span>
      </div>
      <div style={{ marginTop: 6, height: 3, background: "var(--bg3)", borderRadius: 2 }}>
        <div style={{ height: "100%", width: `${Math.min(Math.abs(pct), 100)}%`, background: color, borderRadius: 2 }} />
      </div>
    </div>
  );
}
