"use client";

import React, { useMemo, useState } from "react";
import { ScreenHeader } from "@/components/layout/ScreenHeader";
import { Donut } from "@/components/charts/Donut";
import { useAuth } from "@/lib/auth";
import { useHoldings } from "@/lib/queries";
import { formatINRShort } from "@/lib/format";

const ASSET_CLASS_COLORS: Record<string, string> = {
  EQUITY:       "oklch(0.76 0.16 195)",
  MUTUAL_FUND:  "oklch(0.73 0.16 145)",
  GOLD:         "oklch(0.82 0.14 80)",
  REAL_ESTATE:  "oklch(0.6 0.12 270)",
  FIXED_INCOME: "oklch(0.76 0.16 65)",
  CASH:         "oklch(0.73 0.16 145)",
};

function assetColor(assetClass: string): string {
  return ASSET_CLASS_COLORS[assetClass.toUpperCase()] ?? "var(--text-3)";
}

function assetTypeLabel(assetClass: string): string {
  const labels: Record<string, string> = {
    EQUITY: "EQ", MUTUAL_FUND: "MF", GOLD: "GOLD",
    REAL_ESTATE: "RE", FIXED_INCOME: "FI", CASH: "CASH",
  };
  return labels[assetClass.toUpperCase()] ?? assetClass.slice(0, 3).toUpperCase();
}

type FilterType = "all" | string;

export default function InvestmentsPage() {
  const { owner } = useAuth();
  const ownerId = owner?.owner_id;
  const { data: holdingsData, isLoading } = useHoldings(ownerId);

  const holdings = holdingsData ?? [];

  // Distinct asset classes for filter tabs
  const assetClasses = useMemo(
    () => Array.from(new Set(holdings.map((h) => h.asset_class))),
    [holdings]
  );

  const [filter, setFilter] = useState<FilterType>("all");
  const filtered = filter === "all" ? holdings : holdings.filter((h) => h.asset_class === filter);

  // KPIs
  const totalCurrentPaise = useMemo(() => holdings.reduce((s, h) => s + (h.current_value_paise ?? 0), 0), [holdings]);
  const totalInvestedPaise = useMemo(() => holdings.reduce((s, h) => s + (h.purchase_price_paise ?? 0), 0), [holdings]);
  const totalPLPaise = totalCurrentPaise - totalInvestedPaise;

  // Sectors (by asset_class)
  const sectors = useMemo(() => {
    if (totalCurrentPaise === 0) return [];
    const byClass = new Map<string, number>();
    for (const h of holdings) {
      const cls = h.asset_class;
      byClass.set(cls, (byClass.get(cls) ?? 0) + (h.current_value_paise ?? 0));
    }
    return Array.from(byClass.entries())
      .sort(([, a], [, b]) => b - a)
      .map(([cls, val]) => ({
        name: cls.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
        pct: Math.round((val / totalCurrentPaise) * 100),
        color: assetColor(cls),
      }));
  }, [holdings, totalCurrentPaise]);

  const donutSegments = sectors.map((s) => ({ value: s.pct, color: s.color }));

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <ScreenHeader
        title="Portfolio"
        subtitle={`${holdings.length} holding${holdings.length !== 1 ? "s" : ""} · Direct equity + mutual funds`}
        live
        actions={<ActionBtn color="oklch(0.76 0.16 195)">+ Add Holding</ActionBtn>}
      />

      <div style={{ flex: 1, overflow: "auto", padding: "16px 24px 80px" }}>
        {/* KPI strip */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 14 }}>
          {[
            { label: "Portfolio Value",  val: formatINRShort(totalCurrentPaise),                                     color: "oklch(0.76 0.16 195)" },
            { label: "Today's P&L",      val: "—",                                                                  color: "var(--text-3)"         },
            { label: "Overall P&L",      val: totalPLPaise !== 0 ? formatINRShort(Math.abs(totalPLPaise)) : "—",    color: totalPLPaise >= 0 ? "oklch(0.73 0.16 145)" : "oklch(0.66 0.18 25)" },
            { label: "XIRR",             val: "—",                                                                  color: "var(--text-3)"         },
            { label: "Invested",         val: formatINRShort(totalInvestedPaise),                                   color: "var(--text)"           },
          ].map((k) => (
            <div key={k.label} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 14px" }}>
              <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 6 }}>{k.label}</div>
              <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 18, color: k.color }}>{k.val}</div>
            </div>
          ))}
        </div>

        {/* Sector + allocation */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12, marginBottom: 14 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>Asset Allocation</span>
            </div>
            {sectors.length > 0 ? (
              <>
                <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", gap: 1, marginBottom: 10 }}>
                  {sectors.map((s) => <div key={s.name} style={{ flex: s.pct, background: s.color, opacity: 0.8 }} />)}
                </div>
                <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                  {sectors.map((s) => (
                    <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <div style={{ width: 6, height: 6, borderRadius: "50%", background: s.color }} />
                      <span style={{ fontSize: 11, color: "var(--text-2)" }}>{s.name}</span>
                      <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{s.pct}%</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>No holdings ingested yet</div>
            )}
          </div>

          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600, marginBottom: 8 }}>Allocation</div>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              {donutSegments.length > 0 ? (
                <Donut size={80} segments={donutSegments} />
              ) : (
                <Donut size={80} segments={[{ value: 1, color: "var(--border)" }]} />
              )}
            </div>
          </div>
        </div>

        {/* Filter tabs */}
        <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
          {(["all", ...assetClasses] as FilterType[]).map((k) => {
            const label = k === "all" ? "All" : k.replace("_", " ").charAt(0).toUpperCase() + k.replace("_", " ").slice(1).toLowerCase();
            const active = filter === k;
            return (
              <button key={k} onClick={() => setFilter(k)}
                style={{
                  padding: "5px 14px", borderRadius: 7,
                  border: `1px solid ${active ? "oklch(0.76 0.16 195 / 0.4)" : "var(--border)"}`,
                  background: active ? "oklch(0.76 0.16 195 / 0.08)" : "var(--surface)",
                  color: active ? "oklch(0.76 0.16 195)" : "var(--text-2)",
                  fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                }}
              >{label}</button>
            );
          })}
        </div>

        {/* Holdings table */}
        {isLoading ? (
          <div style={{ fontSize: 13, color: "var(--text-3)", padding: "20px 0" }}>Loading holdings…</div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: "var(--text-3)", fontSize: 13 }}>
            No holdings found. Ingest a MF CAS or Zerodha statement to populate this view.
          </div>
        ) : (
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid var(--border)" }}>
                  {["Holding", "Type", "Avg Buy", "LTP / NAV", "P&L", "P&L %", "XIRR", "Day"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "8px 14px", fontSize: 10, color: "var(--text-3)", fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((h) => {
                  const up = (h.pl_paise ?? 0) >= 0;
                  const avgDisplay = h.avg_cost_paise != null ? formatINRShort(h.avg_cost_paise) : "—";
                  const ltpDisplay = h.nav_paise != null ? formatINRShort(h.nav_paise) : "—";
                  const plDisplay = h.pl_paise != null ? `${h.pl_paise >= 0 ? "+" : ""}${formatINRShort(Math.abs(h.pl_paise))}` : "—";
                  const plPctDisplay = h.pl_pct != null ? `${h.pl_pct >= 0 ? "+" : ""}${h.pl_pct.toFixed(1)}%` : "—";
                  return (
                    <HoldingRow
                      key={h.id}
                      name={h.instrument_name}
                      type={assetTypeLabel(h.asset_class)}
                      typeColor={assetColor(h.asset_class)}
                      avg={avgDisplay}
                      ltp={ltpDisplay}
                      pl={plDisplay}
                      plp={plPctDisplay}
                      xirr="—"
                      day="—"
                      up={up}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function HoldingRow({ name, type, typeColor, avg, ltp, pl, plp, xirr, day, up }: {
  name: string; type: string; typeColor: string;
  avg: string; ltp: string; pl: string; plp: string;
  xirr: string; day: string; up: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const gain = "oklch(0.73 0.16 145)";
  const loss = "oklch(0.66 0.18 25)";
  return (
    <tr
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ borderBottom: "1px solid var(--border)", cursor: "pointer", background: hovered ? "rgba(255,255,255,0.025)" : "transparent" }}
    >
      <td style={{ padding: "10px 14px", fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{name}</td>
      <td style={{ padding: "10px 14px" }}>
        <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, background: typeColor + "18", color: typeColor, fontWeight: 600, textTransform: "uppercase" }}>{type}</span>
      </td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: "var(--text-2)", fontFamily: "JetBrains Mono, monospace" }}>{avg}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: "var(--text)", fontFamily: "JetBrains Mono, monospace" }}>{ltp}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: pl === "—" ? "var(--text-3)" : up ? gain : loss, fontFamily: "JetBrains Mono, monospace" }}>{pl}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: plp === "—" ? "var(--text-3)" : up ? gain : loss, fontFamily: "JetBrains Mono, monospace" }}>{plp}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{xirr}</td>
      <td style={{ padding: "10px 14px", fontSize: 12, color: "var(--text-3)", fontFamily: "JetBrains Mono, monospace" }}>{day}</td>
    </tr>
  );
}

function ActionBtn({ children, color }: { children: React.ReactNode; color: string }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ padding: "6px 14px", background: hovered ? color + "20" : color + "10", border: `1px solid ${color + "30"}`, borderRadius: 8, color, fontSize: 12, cursor: "pointer", fontFamily: "inherit", transition: "all 0.15s" }}
    >{children}</button>
  );
}
